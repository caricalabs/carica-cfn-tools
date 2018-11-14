import datetime
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.parse

import boto3
import yaml

STACK_CAPABILITIES = ['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM']


class ConfigError(Exception):
    pass


class AwsCliError(Exception):
    pass


class StackConfig(object):
    def __init__(self, config_file, templates_dir=None):
        self.config_file = config_file
        self.stack_config = self._load_config()
        self.template_file = os.path.join(templates_dir or self.default_template_dir(),
                                          self.stack_config['Template'])
        self.boto_params = self._load_boto_params()

    @staticmethod
    def default_template_dir():
        return os.path.join(sys.path[0], 'templates')

    def _load_config(self):
        with open(self.config_file, 'r') as stream:
            stack_config = yaml.load(stream)
            for attr in ['Region', 'Bucket', 'Name', 'Template']:
                if attr not in stack_config:
                    raise ConfigError(f'Config file {self.config_file} is missing the '
                                      f'required top-level key "{attr}"')
            return stack_config

    def _load_boto_params(self):
        params = self.stack_config.get('Parameters', {})

        if not isinstance(params, dict):
            raise ConfigError('Top-level key "Parameters" must be a dictionary '
                              '(not a list or other type)')

        def val(v):
            if v is False:
                return "false"
            if v is True:
                return "true"
            return str(v)

        return [{'ParameterKey': k, 'ParameterValue': val(v)} for k, v in params.items()]

    @staticmethod
    def _print_fs_tree(path):
        for root, _, files in os.walk(path):
            for file in files:
                relative_path = os.path.join(root, file)[len(path) + 1:]
                print('  ' + relative_path)

    def _package_template(self):
        # Prepare a temporary directory to run the package operation from, so relative
        # paths can be expanded using the correct "extras" listed in the stack config file.
        with tempfile.TemporaryDirectory(prefix='stack_') as temp_dir:
            stack_config_dir = os.path.dirname(self.config_file)

            # Copy the template file itself
            template_file_name = os.path.basename(self.template_file)
            temp_template_file_name = os.path.join(temp_dir, template_file_name)
            shutil.copyfile(self.template_file, temp_template_file_name)

            # Copy all the referenced extras
            for extra in self.stack_config.get('Extras', []):
                extra_path = os.path.abspath(os.path.join(stack_config_dir, extra))
                if not os.path.exists(extra_path):
                    raise ConfigError(f'Extra "{extra_path}" does not exist"')

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
            stack_name = self.stack_config['Name']
            bucket = self.stack_config['Bucket']
            args = [
                'aws', 'cloudformation', 'package',
                '--template-file', temp_template_file_name,
                '--s3-bucket', bucket,
                '--s3-prefix', f'{stack_name}/extras',
            ]
            print(f'Packaging extras in s3://{bucket}/{stack_name}/extras')
            proc = subprocess.Popen(args, cwd=temp_dir, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            stdout, stderr = proc.communicate()
            if proc.returncode != 0:
                raise AwsCliError('CLI package step failed')

            # stdout contains the processed YAML template
            return stdout

    def _upload_template(self, stack_yaml):
        s3 = boto3.client('s3', region_name=self.stack_config['Region'])
        stack_name = self.stack_config['Name']
        bucket = self.stack_config['Bucket']
        key = f'{stack_name}/{stack_name}.yml'
        template_s3_uri = f's3://{bucket}/{key}'
        print(f'Uploading template to {template_s3_uri}')
        s3.put_object(Bucket=bucket, Key=key, Body=stack_yaml)
        return key

    def _upload_stack_artifacts(self):
        stack_yaml = self._package_template()
        template_key = self._upload_template(stack_yaml)
        template_https_url = get_s3_https_url(self.stack_config['Region'],
                                              self.stack_config['Bucket'],
                                              template_key)
        return template_https_url

    def create_change_set(self, change_set_type='CREATE'):
        region = self.stack_config['Region']
        change_set_name = datetime.datetime.utcnow().strftime('C-%Y-%m-%d-%H%M%SZ')

        template_https_url = self._upload_stack_artifacts()
        cfn = boto3.client('cloudformation', region_name=region)
        cfn.validate_template(TemplateURL=template_https_url)
        response = cfn.create_change_set(
            StackName=self.stack_config['Name'],
            TemplateURL=template_https_url,
            Parameters=self.boto_params,
            Capabilities=STACK_CAPABILITIES,
            ChangeSetName=change_set_name,
            ChangeSetType=change_set_type
        )

        # Must set "safe" so slashes in the ARNs get escaped as well
        quoted_stack_arn = urllib.parse.quote(response['StackId'], safe='')
        quoted_change_set_arn = urllib.parse.quote(response['Id'], safe='')
        console_url = f'https://console.aws.amazon.com/cloudformation/home?region={region}#' \
                      f'/stacks/{quoted_stack_arn}/changesets/{quoted_change_set_arn}/changes'
        open_url(console_url)
