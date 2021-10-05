import copy
import datetime
import os
import random
import re
import shutil
import string
import subprocess
import sys
import tempfile
from collections import OrderedDict
from enum import Enum
from pathlib import Path

import boto3
import botocore.exceptions
import yaml
from jinja2 import Environment, FileSystemLoader
from samtranslator.translator.managed_policy_translator import ManagedPolicyLoader
from samtranslator.translator.transform import transform

from carica_cfn_tools.utils import open_url_in_browser, get_s3_https_url, update_dict, \
    get_cfn_console_url_changeset, copy_dict, load_cfn_template, dump_cfn_template_yaml, \
    dump_cfn_template_json, get_cfn_console_url_stack

STACK_CAPABILITIES = ['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM', 'CAPABILITY_AUTO_EXPAND']


class Action(Enum):
    CREATE = 'create'
    UPDATE = 'update'
    CREATE_OR_UPDATE = 'create_or_update'


class CaricaCfnToolsError(Exception):
    pass


class Stack(object):
    def __init__(self, config_file, include_templates=None, convert_sam_to_cfn=False, extras=None, jinja=False,
                 jextras=None, verbose=False):
        self.config_file = config_file
        self.include_templates = include_templates
        self.convert_sam_to_cfn = convert_sam_to_cfn
        self.jinja = jinja
        self.verbose = verbose
        self._load_stack_config(extras, jextras)

        # For un-SAM'ing templates
        iam = boto3.client('iam', region_name=self.region)
        self.managed_policy_loader = ManagedPolicyLoader(iam)

        # More aggressive than the default
        self.waiter_config = {'Delay': 3, 'MaxAttempts': 200}

    def _load_stack_config(self, extras, jextras):
        """
        Load the stack config YAML file, validate some settings, and store the results
        in self.
        """
        if not os.path.isfile(self.config_file):
            raise CaricaCfnToolsError(f'Stack config file "{self.config_file}" not found')

        config_dir = os.path.dirname(self.config_file)
        with open(self.config_file, 'r') as stream:
            config = yaml.load(stream, Loader=yaml.SafeLoader)
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
                raise CaricaCfnToolsError('Top-level key "Extras" must be a list of glob patterns '
                                          '(not a dictionary or other type) if it is present')
            if extras:
                self.extras += extras

            self.jextras = config.get('JinjaExtras', [])
            if not isinstance(self.jextras, list):
                raise CaricaCfnToolsError('Top-level key "JinjaExtras" must be a list of glob patterns '
                                          '(not a dictionary or other type) if it is present')
            if jextras:
                self.jextras += jextras

            self.jextras_context = config.get('JinjaExtrasContext', {})
            if not isinstance(self.jextras_context, dict):
                raise CaricaCfnToolsError('Top-level key "JinjaExtrasContext" must be a dictionary '
                                          '(not a list or other type) if it is present')

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
            raise CaricaCfnToolsError(f'Template "{template_path}" not found')

        if self.jinja:
            # Let Jinja load the file so errors include line number information
            template_str = self._run_jinja_on_main_template(template_path)
            if self.verbose:
                print(f'Stack template "{template_path}" after Jinja processing: ')
                print('-----------------------------------------------------------------------')
                print(template_str)
                print('-----------------------------------------------------------------------')
        else:
            with open(template_path, 'r') as stream:
                template_str = stream.read()

        template_data, template_type = load_cfn_template(template_str)
        return template_str, template_type, template_data

    def _apply_includes(self, template_data, included_data):
        """
        Replaces "IncludedResources" in template_data with items that match the name
        in included_data.

        :param template_data: the template to process transforms in
        :param included_data: the template to read included resources from
        :return: the transformed template
        """

        # Make copies so we don't alter the inputs
        template_data = copy.deepcopy(template_data)
        included_data = copy.deepcopy(included_data)

        t_i_resources = template_data.get('IncludedResources', {})
        t_resources = template_data.get('Resources', {})
        i_resources = included_data.get('Resources', {})

        # Try to find each "IncludedResources" item in the included data's "Resources"
        # section using the included resource's name as a regular expression.  Merge
        # sub-keys in the main template with the included resource's keys.  Since the
        # included resource is removed if a match is found, the first included template
        # with a match "wins".
        for t_i_key_pattern, t_i_value in list(t_i_resources.items()):
            if not isinstance(t_i_value, dict):
                raise CaricaCfnToolsError(f'IncludedResources item "{t_i_key_pattern}" must have a '
                                          'dict value (use {} for empty)')

            pat = re.compile(f'^{t_i_key_pattern}$')
            for i_key in i_resources.keys():
                if pat.match(i_key):
                    if self.verbose:
                        print(
                            f'IncludedResources pattern "{pat.pattern}" matches resource "{i_key}"')
                    i_value = i_resources.get(i_key, {})
                    t_resources[i_key] = update_dict(i_value, t_i_value)
                    del t_i_resources[t_i_key_pattern]
                    break

        return template_data

    def _aws_cfn_package_and_upload_extras(self, template_str):
        """
        Use "aws cloudformation package" to upload referenced objects (but not the template
        itself) to S3.  Also upload the extras to S3.

        :param template_str: the template whose resources should be uploaded
        :return: a tuple containing the packaged template as a string, the format of that template
        (yaml or json), and the structured packaged template data dict
        """

        # Prepare a temporary directory to run the package operation from, so relative
        # paths can be expanded using the correct "extras" listed in the stack config file.
        temp_dir = None
        try:
            temp_dir = tempfile.mkdtemp(prefix='stack_')

            # Write the template file itself
            template_file_name = os.path.basename(self.template)
            temp_template_file_name = os.path.join(temp_dir, template_file_name)
            with open(temp_template_file_name, 'w') as stream:
                stream.write(template_str)

            # Expand all the extra glob patterns to path strings (can be absolute or relative)
            glob_root_path = os.path.dirname(self.config_file)
            extra_paths = self._expand_globs(glob_root_path, self.extras)
            jextra_paths = self._expand_globs(glob_root_path, self.jextras)

            # Copy all the extras to the temp dir
            all_temp_extra_paths = []
            temp_jextra_paths = []
            for path in set(extra_paths + jextra_paths):
                if not os.path.exists(path):
                    raise CaricaCfnToolsError(f'Extra "{path}" does not exist"')

                last_part = os.path.basename(path)
                temp_extra_path = os.path.join(temp_dir, last_part)

                if os.path.isdir(path):
                    shutil.copytree(path, temp_extra_path)
                else:
                    shutil.copyfile(path, temp_extra_path)

                all_temp_extra_paths.append(temp_extra_path)
                if path in jextra_paths:
                    temp_jextra_paths.append(temp_extra_path)

            # Run Jinja after everything is in place
            for path in set(temp_jextra_paths):
                self._run_jinja_on_extra(temp_dir, path)

            # Upload all extras so they can be used by stack resources.
            for temp_extra_path in all_temp_extra_paths:
                s3_path = f's3://{self.bucket}/{self.stack_name}/extras/{os.path.basename(temp_extra_path)}'

                args = ['aws', 's3', 'cp']
                if os.path.isdir(temp_extra_path):
                    args += ['--recursive']
                args += [temp_extra_path, s3_path]

                proc = subprocess.Popen(args, cwd=temp_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                stdout, stderr = proc.communicate()
                if proc.returncode != 0:
                    self._handle_failed_subprocess(proc, stdout, stderr)

            # Invoke the AWS CLI to package artifacts referred to by the template in
            # sections it understands (Lambda deployment archives, etc.).
            with tempfile.NamedTemporaryFile() as output_temporary_file:
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
                self._handle_failed_subprocess(proc, stdout, stderr)

            p_template_data, p_template_type = load_cfn_template(p_template_str)
            return p_template_str, p_template_type, p_template_data
        except CaricaCfnToolsError:
            print(f'\nPackaging temp directory preserved:', file=sys.stderr)
            sys.stderr.flush()
            os.system(f'ls -laR {temp_dir} 1>&2')
            print('\n', file=sys.stderr)
            sys.stderr.flush()

            # Prevent the temp dir from getting removed
            temp_dir = None

            raise
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

        # Convert from SAM to CFN if desired
        template_data = self._normalize_template_format(template_data)

        if self.verbose:
            print(f'Stack template "{os.path.abspath(self.template)}": ')
            print('-----------------------------------------------------------------------')
            print(dump_cfn_template_yaml(template_data))
            print('-----------------------------------------------------------------------')

        # Process each included template in order
        for include_template in self.include_templates:
            print(f'Loading included template "{os.path.abspath(include_template)}"...')
            include_str, include_type, include_data = self._load_template(include_template)

            # We must run "aws cloudformation package" on the included template to expand
            # references to local resources (like a CodeUri of "./deployment.zip") before
            # we can apply transforms.  Applying transforms may require normalizing
            # from SAM to CFN and that will fail if "./deployment.zip" is still in the
            # template.  It doesn't hurt to run "cloudformation package" again later in
            # this function, since it will compute the same resource names the second time
            # and skip uploading them based on S3 ETag.
            print(f'Packaging included template "{os.path.abspath(include_template)}"...')
            p_include_str, p_include_type, p_include_data = self._aws_cfn_package_and_upload_extras(include_str)

            # Convert from SAM to CFN if desired
            p_include_data = self._normalize_template_format(p_include_data)

            if self.verbose:
                print(f'Included template "{os.path.abspath(include_template)}": ')
                print('-----------------------------------------------------------------------')
                print(dump_cfn_template_yaml(p_include_data))
                print('-----------------------------------------------------------------------')

            print(f'Including resources from "{os.path.abspath(include_template)}"...')
            template_data = self._apply_includes(template_data, p_include_data)

        # If we applied includes, dump the template data back to a string for later use
        if self.include_templates:
            if self.verbose:
                print(f'Stack template "{os.path.abspath(self.template)}" after includes applied: ')
                print('-----------------------------------------------------------------------')
                print(dump_cfn_template_yaml(template_data))
                print('-----------------------------------------------------------------------')

            if len(template_data.get('IncludedResources', {})) > 0:
                raise CaricaCfnToolsError(
                    'The following IncludedResources did not match a resource in any included '
                    'templates: ' + ', '.join(template_data['IncludedResources'].keys()))

            del template_data['IncludedResources']

            if template_type == 'yaml':
                template_str = dump_cfn_template_yaml(template_data)
            else:
                template_str = dump_cfn_template_json(template_data)

        print(f'Packaging template resources...')
        p_template_str, p_template_type, p_template_data = self._aws_cfn_package_and_upload_extras(template_str)

        print(f'Uploading template...')
        template_key = self._upload_template(p_template_str)
        print(f'Template uploaded at s3://{self.bucket}/{template_key}')

        # Return the full HTTPS URL to the template in the S3 bucket
        return get_s3_https_url(self.region, self.bucket, template_key)

    def apply_change_set(self, action, wait, ignore_empty_updates, role_arn):
        template_https_url = self._publish()
        cfn = boto3.client('cloudformation', region_name=self.region)
        cfn.validate_template(TemplateURL=template_https_url)

        # Compute the correct change set type based on the action and current state
        if action is Action.CREATE or (action is Action.CREATE_OR_UPDATE and not self._stack_exists()):
            change_set_type = 'CREATE'
        else:
            change_set_type = 'UPDATE'

        # Change set names are quite restrictive (must start with a letter, no colons).
        change_set_name = datetime.datetime.utcnow().strftime('C-%Y-%m-%d-%H%M%SZ')

        args = dict(StackName=self.stack_name,
                    TemplateURL=template_https_url,
                    Parameters=self.params,
                    Capabilities=STACK_CAPABILITIES,
                    ChangeSetName=change_set_name,
                    ChangeSetType=change_set_type)

        if role_arn:
            args['RoleARN'] = role_arn

        try:
            response = cfn.create_change_set(**args)

            if wait:
                waiter = cfn.get_waiter('change_set_create_complete')
                waiter.wait(ChangeSetName=change_set_name, StackName=self.stack_name, WaiterConfig=self.waiter_config)
        except botocore.exceptions.WaiterError as e:
            # We can discover if the changeset was empty by querying it after the waiter fails.
            response = cfn.describe_change_set(ChangeSetName=change_set_name, StackName=self.stack_name)
            if response['Status'] == 'FAILED' and response['StatusReason'].startswith(
                    '''The submitted information didn't contain changes.'''):
                if ignore_empty_updates:
                    print(f'Change set {change_set_name} contains no changes, deleting')
                    cfn.delete_change_set(ChangeSetName=change_set_name, StackName=self.stack_name)
                    return
                else:
                    # Raise a better error than "Waiter encountered a terminal failure state" since
                    # we know what happened.
                    raise CaricaCfnToolsError(response['StatusReason'])

            raise CaricaCfnToolsError(str(e))
        except botocore.exceptions.ClientError as e:
            raise CaricaCfnToolsError(str(e))

        console_url = get_cfn_console_url_changeset(self.region, response['StackId'], response['Id'])
        open_url_in_browser(console_url)

    def apply_stack(self, action, wait, ignore_empty_updates, role_arn):
        template_https_url = self._publish()
        cfn = boto3.client('cloudformation', region_name=self.region)
        cfn.validate_template(TemplateURL=template_https_url)

        waiter = None
        try:
            if action is Action.CREATE or (action is Action.CREATE_OR_UPDATE and not self._stack_exists()):
                args = dict(StackName=self.stack_name,
                            TemplateURL=template_https_url,
                            Parameters=self.params,
                            Capabilities=STACK_CAPABILITIES)

                if role_arn:
                    args['RoleARN'] = role_arn

                response = cfn.create_stack(**args)
                if wait:
                    waiter = cfn.get_waiter('stack_create_complete')
            else:
                args = dict(StackName=self.stack_name,
                            TemplateURL=template_https_url,
                            Parameters=self.params,
                            Capabilities=STACK_CAPABILITIES)

                if role_arn:
                    args['RoleARN'] = role_arn

                response = cfn.update_stack(**args)
                if wait:
                    waiter = cfn.get_waiter('stack_update_complete')
        except botocore.exceptions.ClientError as e:
            if ignore_empty_updates and e.response['Error']['Message'] == 'No updates are to be performed.':
                print(f'Template contains no changes')
                return

            raise CaricaCfnToolsError(str(e))

        console_url = get_cfn_console_url_stack(self.region, response['StackId'])
        open_url_in_browser(console_url)

        if waiter:
            waiter.wait(StackName=self.stack_name, WaiterConfig=self.waiter_config)

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

    def _run_jinja_on_main_template(self, template_path):
        env = Environment(loader=FileSystemLoader([os.path.dirname(template_path)]))
        print(f'Processing main template with Jinja')
        template = env.get_template(os.path.basename(template_path))
        context = {
            # A short string of ASCII chars that is randomly generated for each deployment
            'deploy_stamp': ''.join(random.choice(string.ascii_letters) for _ in range(6)),
        }
        return template.render(**context)

    def _run_jinja_on_extra(self, temp_dir, path):
        env = Environment(loader=FileSystemLoader([temp_dir]))

        file_paths = []
        if os.path.isdir(path):
            file_paths.extend([str(f) for f in Path(path).rglob('*') if f.is_file()])
        else:
            file_paths.append(path)

        for file_path in file_paths:
            print(f'Processing Jinja extra {file_path}')
            # FileSystemLoader expects paths relative to one of its search paths.
            template = env.get_template(os.path.relpath(file_path, temp_dir))
            output = template.render(**self.jextras_context)

            with tempfile.NamedTemporaryFile(prefix='jinja_', delete=False) as output_file:
                output_file.write(bytes(output, 'utf-8'))
                os.rename(output_file.name, file_path)

    def _expand_globs(self, root_path, paths_or_patterns):
        """Expand glob patterns from the given root into a list of absolute paths"""
        abs_paths = []
        for path_or_pattern in paths_or_patterns:
            if os.path.isabs(path_or_pattern):
                abs_paths.append(path_or_pattern)
            else:
                path_objs = list(Path(root_path).rglob(path_or_pattern))
                if path_objs:
                    abs_paths.extend(str(p.absolute()) for p in path_objs)
                else:
                    print(f'Warning: glob pattern "{path_or_pattern}" matches nothing from root "{root_path}"')
        return abs_paths

    def _stack_exists(self):
        """Check if a non-deleted stack exists with the this config's name"""
        cfn = boto3.client('cloudformation', region_name=self.region)
        try:
            response = cfn.describe_stacks(StackName=self.stack_name)
            return len(response['Stacks']) > 0
        except botocore.exceptions.ClientError as e:
            # The code is not distinct ("ValidationError"), so check the message
            if e.response['Error']['Message'].endswith('does not exist'):
                return False
            raise e

    def _handle_failed_subprocess(self, proc, stdout, stderr):
        # Write both to stderr so it all comes out serially and in error logs
        sys.stderr.write(str(stdout, 'utf-8'))
        sys.stderr.write(str(stderr, 'utf-8'))
        cmd = ' '.join(f'"{a}"' for a in proc.args)
        raise CaricaCfnToolsError(f'Subprocess failed; see previous output for details: {cmd}')
