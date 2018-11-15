import copy
import datetime
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import OrderedDict

import boto3
import yaml
from samtranslator.translator.managed_policy_translator import ManagedPolicyLoader
from samtranslator.translator.transform import transform

from carica_cfn_tools.utils import open_url_in_browser, get_s3_https_url, update_dict, \
    get_cfn_console_url, copy_dict, load_cfn_template, dump_cfn_template_yaml, \
    dump_cfn_template_json

STACK_CAPABILITIES = ['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM']


class CaricaCfnToolsError(Exception):
    pass


class Stack(object):
    def __init__(self, config_file, base_template=None, print_templates=False, extras=None,
                 convert_sam_to_cfn=False):
        self.convert_sam_to_cfn = convert_sam_to_cfn
        self.print_templates = print_templates
        self.config_file = config_file
        self.base_template = base_template
        self._load_stack_config(extras)

        # For un-SAM'ing templates
        iam = boto3.client('iam', region_name=self.region)
        self.managed_policy_loader = ManagedPolicyLoader(iam)

    def _load_stack_config(self, extras):
        """
        Load the stack config YAML file, validate some settings, and store the results
        in self.
        """
        if not os.path.isfile(self.config_file):
            raise CaricaCfnToolsError(f'Stack config file "{self.config_file}" not found')

        config_dir = os.path.dirname(self.config_file)
        with open(self.config_file, 'r') as stream:
            config = yaml.load(stream)
            for attr in ['Region', 'Bucket', 'Name', 'Template']:
                if attr not in config:
                    raise CaricaCfnToolsError(f'Stack config file "{self.config_file}" '
                                              f'is missing the required top-level key "{attr}"')
            self.region = config['Region']
            self.bucket = config['Bucket']
            self.stack_name = config['Name']

            self.template = os.path.join(config_dir, config['Template'])
            if not os.path.isfile(self.template):
                raise CaricaCfnToolsError(f'Referenced template file "{self.template}" '
                                          f'does not exist')

            self.extras = config.get('Extras', [])
            if not isinstance(self.extras, list):
                raise CaricaCfnToolsError('Top-level key "Extras" must be a list '
                                          '(not a dictionary or other type) if it is present')
            if extras:
                self.extras += extras

            params = config.get('Parameters', {})
            if not isinstance(params, dict):
                raise CaricaCfnToolsError('Top-level key "Parameters" must be a dictionary '
                                          '(not a list or other type) if it is present')

            # Resolve external parameter values
            for name, value in params.items():
                if isinstance(value, dict):
                    if 'SecretsManager' in value:
                        params[name] = self._load_secrets_manager_value(value['SecretsManager'])
                    if 'ParameterStore' in value:
                        params[name] = self._load_parameter_store_value(value['ParameterStore'])

            def val(v):
                if v is False:
                    return "false"
                if v is True:
                    return "true"
                return str(v)

            self.params = [{'ParameterKey': k, 'ParameterValue': val(v)} for k, v in params.items()]

    def _load_template(self, template_path):
        """
        Loads the template file.

        :return: a tuple containing the template as a string, the format of that template
        (yaml or json), and the structured template data dict
        """

        if not os.path.isfile(template_path):
            raise CaricaCfnToolsError(f'Template file "{template_path}" not found')

        with open(template_path, 'r') as stream:
            template_str = stream.read()

        template_data, template_type = load_cfn_template(template_str)
        return template_str, template_type, template_data

    def _apply_carica_transforms(self, template_data, base_data):
        """
        Processes any "Carica::*" transforms in template_data using base_data.

        :param template_data: the template to process transforms in
        :param base_data: the template to read base data from
        :return: the transformed template
        """

        # Make copies so we don't alter the inputs
        template_data = self._normalize_template_format(copy.deepcopy(template_data))
        base_data = self._normalize_template_format(copy.deepcopy(base_data))

        if self.print_templates:
            print('Normalized base: ')
            print('-----------------------------------------------------------------------')
            print(dump_cfn_template_yaml(base_data))
            print('-----------------------------------------------------------------------')
            print('Normalized template: ')
            print('-----------------------------------------------------------------------')
            print(dump_cfn_template_yaml(template_data))
            print('-----------------------------------------------------------------------')

        t_b_resources = template_data.get('BaseResources', {})
        t_resources = template_data.get('Resources', {})
        b_resources = base_data.get('Resources', {})

        # Convert each "BaseResource" item into a regular resource by finding the
        # resource in the base template using the BaseResource name as a regular
        # expression, then merging any properties with the base value.
        for t_b_name, t_b_value in list(t_b_resources.items()):
            if not isinstance(t_b_value, dict):
                raise CaricaCfnToolsError(f'BaseResource "{t_b_name}" must have a dict value '
                                          '(try {})')

            pat = re.compile(f'^{t_b_name}$')
            matches = [pat.match(b_key) for b_key in b_resources.keys()]
            matches = list(filter(None.__ne__, matches))
            if len(matches) != 1:
                raise CaricaCfnToolsError(f'Expected template BaseResource "{t_b_name}" to match '
                                          f'as a regular expression to exactly one resource '
                                          f'in base template, but matched {len(matches)}')
            b_name = matches[0].group()
            b_value = b_resources.get(b_name, {})
            t_resources[b_name] = update_dict(b_value, t_b_value)

        del template_data['BaseResources']
        return template_data

    def _aws_cfn_package(self, template_str):
        """
        Use "aws cloudformation package" to upload referenced objects (but not the template
        itself) to S3.

        :param template_str: the template whose resources should be uploaded
        :return: a tuple containing the packaged template as a string, the format of that template
        (yaml or json), and the structured packaged template data dict
        """

        # Prepare a temporary directory to run the package operation from, so relative
        # paths can be expanded using the correct "extras" listed in the stack config file.
        temp_dir = None
        try:
            temp_dir = tempfile.mkdtemp(prefix='stack_')
            stack_config_dir = os.path.dirname(self.config_file)

            # Write the template file itself
            template_file_name = os.path.basename(self.template)
            temp_template_file_name = os.path.join(temp_dir, template_file_name)
            with open(temp_template_file_name, 'w') as stream:
                stream.write(template_str)

            # Copy all the referenced extras
            for extra in self.extras:
                extra_path = os.path.abspath(os.path.join(stack_config_dir, extra))
                if not os.path.exists(extra_path):
                    raise CaricaCfnToolsError(f'Extra "{extra_path}" does not exist"')

                extra_last_part = os.path.basename(extra_path)
                temp_extra_path = os.path.join(temp_dir, extra_last_part)
                if os.path.isdir(extra_path):
                    shutil.copytree(extra_path, temp_extra_path)
                else:
                    shutil.copyfile(extra_path, temp_extra_path)

            with tempfile.NamedTemporaryFile() as output_temporary_file:
                # Let the AWS CLI upload everything to S3
                args = [
                    'aws', 'cloudformation', 'package',
                    '--template-file', temp_template_file_name,
                    '--s3-bucket', self.bucket,
                    '--s3-prefix', f'{self.stack_name}/extras',
                    '--output-template-file', f'{output_temporary_file.name}',
                ]
                proc = subprocess.Popen(args, cwd=temp_dir, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)
                stdout, stderr = proc.communicate()

                # Read the transformed template.  We have to write it to a file instead of
                # reading stdin, because the command line can write upload progress messages
                # to stdin in addition to the template file.
                with open(output_temporary_file.name, 'r') as stream:
                    p_template_str = stream.read()

            if proc.returncode != 0:
                # Write both to stder so it all comes out serially
                sys.stderr.write(str(stdout, 'utf-8'))
                sys.stderr.write(str(stderr, 'utf-8'))

                print(f'\nPackaging temp directory preserved:', file=sys.stderr)
                os.system(f'ls -laR {temp_dir} 1>&2')
                print('\n', file=sys.stderr)

                # Prevent the temp dir from getting removed
                temp_dir = None

                raise CaricaCfnToolsError('"aws cloudformation package" step failed; see '
                                          'previous output for details')

            p_template_data, p_template_type = load_cfn_template(p_template_str)
            return p_template_str, p_template_type, p_template_data
        finally:
            if temp_dir:
                shutil.rmtree(temp_dir)

    def _upload_template(self, template_str):
        """
        Upload the template to S3 near where the referenced resources were uploaded.

        :param template_str: the template content to upload to S3
        :return: the S3 key where the template was uploaded.
        """
        s3 = boto3.client('s3', region_name=self.region)

        base, ext = os.path.splitext(self.template)
        if not ext:
            ext = '.txt'

        key = f'{self.stack_name}/{self.stack_name}{ext}'
        s3.put_object(Bucket=self.bucket, Key=key, Body=bytes(template_str, 'utf-8'))
        return key

    def _publish(self):
        """
        Prepare, process, and upload all stack artifacts and the template for this config.

        :return: the HTTPS URL to the template file in S3
        """
        print(f'Loading template...')
        template_str, template_type, template_data = self._load_template(self.template)

        if self.base_template:
            print(f'Loading base template...')
            base_str, base_type, base_data = self._load_template(self.base_template)

            # We must run "aws cloudformation package" on the base template to expand
            # references to local resources (like a CodeUri of "./deployment.zip") before
            # we can apply transforms.  Applying transforms may require normalizing
            # from SAM to CFN and that will fail if "./deployment.zip" is still in the
            # template.  It doesn't hurt to run "cloudformation package" again later in
            # this function, since it will compute the same resource names the second time
            # and skip uploading them based on S3 ETag.
            print(f'Packaging base template resources...')
            p_base_str, p_base_type, p_base_data = self._aws_cfn_package(base_str)

            print(f'Applying Carica transforms...')
            template_data = self._apply_carica_transforms(template_data, p_base_data)

            # Dump the transformed data as the original template type
            if template_type == 'yaml':
                template_str = dump_cfn_template_yaml(template_data)
            else:
                template_str = dump_cfn_template_json(template_data)

        print(f'Packaging template resources...')
        p_template_str, p_template_type, p_template_data = self._aws_cfn_package(template_str)

        print(f'Uploading template...')
        template_key = self._upload_template(p_template_str)
        print(f'Template uploaded at s3://{self.bucket}/{template_key}')

        # Return the full HTTPS URL to the template in the S3 bucket
        return get_s3_https_url(self.region, self.bucket, template_key)

    def create_change_set(self, change_set_type='CREATE'):
        # Change set names are quite restrictive (must start with a letter, no colons).
        change_set_name = datetime.datetime.utcnow().strftime('C-%Y-%m-%d-%H%M%SZ')

        template_https_url = self._publish()

        cfn = boto3.client('cloudformation', region_name=self.region)

        cfn.validate_template(TemplateURL=template_https_url)
        response = cfn.create_change_set(
            StackName=self.stack_name,
            TemplateURL=template_https_url,
            Parameters=self.params,
            Capabilities=STACK_CAPABILITIES,
            ChangeSetName=change_set_name,
            ChangeSetType=change_set_type
        )

        console_url = get_cfn_console_url(self.region, response['StackId'], response['Id'])
        open_url_in_browser(console_url)

    def _load_secrets_manager_value(self, secret_id):
        ssm = boto3.client('secretsmanager', region_name=self.region)
        try:
            return ssm.get_secret_value(SecretId=secret_id)['SecretString']
        except Exception as e:
            raise CaricaCfnToolsError(f'Failed to read Secrets Manager secret '
                                      f'"{secret_id}": {str(e)}')

    def _load_parameter_store_value(self, parameter_name):
        ssm = boto3.client('ssm', region_name=self.region)
        try:
            return ssm.get_parameter(Name=parameter_name, WithDecryption=True)['Parameter']['Value']
        except Exception as e:
            raise CaricaCfnToolsError(f'Failed to read SSM Paramter Store parameter '
                                      f'"{parameter_name}": {str(e)}')

    def _normalize_template_format(self, template_data):
        """
        Normalize the template data as SAM or CloudFormation depending on config.

        :param template_data: the template data to convert from SAM if convert_sam_to_cfn is enabled
        :return: the normalized template data
        """
        if self.convert_sam_to_cfn and template_data.get('Transform') \
                == 'AWS::Serverless-2016-10-31':
            # Make a deep copy of the dict that's mutable (ODict, the type that cfn_flip
            # uses internally, overrides items() to return a new list each time, which foils
            # the transformer).
            template_data = copy_dict(template_data, impl=OrderedDict)
            return transform(template_data, {}, self.managed_policy_loader)
        else:
            return template_data
