import datetime
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.parse

import boto3
import yaml

from carica_cfn_tools.utils import print_fs_tree, open_url_in_browser, get_s3_https_url

STACK_CAPABILITIES = ['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM']


class CaricaCfnToolsError(Exception):
    pass


class StackConfig(object):
    def __init__(self, stack_config_file):
        self.stack_config_file = stack_config_file
        self._load_stack_config()

    def _load_stack_config(self):
        """
        Load the stack config YAML file, validate some settings, and store the results
        in self.
        """
        if not os.path.isfile(self.stack_config_file):
            raise CaricaCfnToolsError(f'Stack config file "{self.stack_config_file}" not found')

        config_dir = os.path.dirname(self.stack_config_file)
        with open(self.stack_config_file, 'r') as stream:
            config = yaml.load(stream)
            for attr in ['Region', 'Bucket', 'Name', 'Template']:
                if attr not in config:
                    raise CaricaCfnToolsError(f'Stack config file "{self.stack_config_file}" '
                                              f'is missing the required top-level key "{attr}"')
            self.region = config['Region']
            self.bucket = config['Bucket']
            self.stack_name = config['Name']

            self.template_path = os.path.join(config_dir, config['Template'])
            if not os.path.isfile(self.template_path):
                raise CaricaCfnToolsError(f'Referenced template file "{self.template_path}" '
                                          f'does not exist')

            self.extras = config.get('Extras', [])
            if not isinstance(self.extras, list):
                raise CaricaCfnToolsError('Top-level key "Extras" must be a list '
                                          '(not a dictionary or other type) if it is present')

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

    def _package_template(self):
        """
        Use "aws cloudformation package" to upload referenced objects (but not the template
        itself) to S3.

        :return: the template content with references rewritten to point to correct the S3 locations
        """

        # Prepare a temporary directory to run the package operation from, so relative
        # paths can be expanded using the correct "extras" listed in the stack config file.
        with tempfile.TemporaryDirectory(prefix='stack_') as temp_dir:
            stack_config_dir = os.path.dirname(self.stack_config_file)

            # Copy the template file itself
            template_file_name = os.path.basename(self.template_path)
            temp_template_file_name = os.path.join(temp_dir, template_file_name)
            shutil.copyfile(self.template_path, temp_template_file_name)

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

            # Print a preview of what's in the temp directory to help users correct include typos
            print(f'Package directory contents ({temp_dir}):')
            print_fs_tree(temp_dir)

            # Let the AWS CLI package it
            args = [
                'aws', 'cloudformation', 'package',
                '--template-file', temp_template_file_name,
                '--s3-bucket', self.bucket,
                '--s3-prefix', f'{self.stack_name}/extras',
            ]
            print(f'Packaging extras in s3://{self.bucket}/{self.stack_name}/extras')
            proc = subprocess.Popen(args, cwd=temp_dir, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            stdout, stderr = proc.communicate()
            if proc.returncode != 0:
                sys.stdout.write(str(stdout, 'utf-8'))
                sys.stderr.write(str(stderr, 'utf-8'))
                raise CaricaCfnToolsError('"aws cloudformation package" step failed; see '
                                          'previous output for details')

            # stdout contains the processed YAML template
            return stdout

    def _upload_template(self, template_content):
        """
        Upload the template to S3 near where the referenced resources were uploaded.

        :param template_content: the template content bytes to upload to S3
        :return: the S3 key where the template was uploaded.
        """
        s3 = boto3.client('s3', region_name=self.region)

        base, ext = os.path.splitext(self.template_path)
        if not ext:
            ext = '.txt'
        key = f'{self.stack_name}/{self.stack_name}{ext}'
        template_s3_uri = f's3://{self.bucket}/{key}'

        print(f'Uploading template to {template_s3_uri}')
        s3.put_object(Bucket=self.bucket, Key=key, Body=template_content)

        return key

    def _upload_stack_artifacts(self):
        """
        Prepare, process, and upload all stack artifacts for this config.

        :return: the HTTPS URL to the processed stack template file in S3
        """
        stack_yaml = self._package_template()
        template_key = self._upload_template(stack_yaml)
        template_https_url = get_s3_https_url(self.region, self.bucket, template_key)
        return template_https_url

    def create_change_set(self, change_set_type='CREATE'):
        change_set_name = datetime.datetime.utcnow().strftime('C-%Y-%m-%d-%H%M%SZ')

        template_https_url = self._upload_stack_artifacts()
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

        # Must set "safe" to exclude '/' so slashes in the ARNs get escaped as well
        quoted_stack_arn = urllib.parse.quote(response['StackId'], safe='')
        quoted_change_set_arn = urllib.parse.quote(response['Id'], safe='')
        console_url = f'https://console.aws.amazon.com/cloudformation/home?region={self.region}#' \
                      f'/stacks/{quoted_stack_arn}/changesets/{quoted_change_set_arn}/changes'
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
