"""
Unit tests for carica_cfn_tools.stack_config module.
"""

import os
from collections import OrderedDict
from unittest.mock import patch, MagicMock

import botocore.exceptions
import pytest
import yaml

from carica_cfn_tools.stack_config import (
    Action,
    CaricaCfnToolsError,
    Stack,
    STACK_CAPABILITIES,
)


class TestAction:
    """Tests for Action enum."""

    def test_create_value(self):
        """Test CREATE enum value."""
        assert Action.CREATE.value == 'create'

    def test_update_value(self):
        """Test UPDATE enum value."""
        assert Action.UPDATE.value == 'update'

    def test_create_or_update_value(self):
        """Test CREATE_OR_UPDATE enum value."""
        assert Action.CREATE_OR_UPDATE.value == 'create_or_update'


class TestCaricaCfnToolsError:
    """Tests for CaricaCfnToolsError exception."""

    def test_exception_inherits_from_exception(self):
        """Test that CaricaCfnToolsError inherits from Exception."""
        assert issubclass(CaricaCfnToolsError, Exception)

    def test_exception_with_message(self):
        """Test exception can be raised with a message."""
        with pytest.raises(CaricaCfnToolsError) as excinfo:
            raise CaricaCfnToolsError("Test error message")
        assert "Test error message" in str(excinfo.value)


class TestStackCapabilities:
    """Tests for STACK_CAPABILITIES constant."""

    def test_contains_iam_capability(self):
        """Test that CAPABILITY_IAM is included."""
        assert 'CAPABILITY_IAM' in STACK_CAPABILITIES

    def test_contains_named_iam_capability(self):
        """Test that CAPABILITY_NAMED_IAM is included."""
        assert 'CAPABILITY_NAMED_IAM' in STACK_CAPABILITIES

    def test_contains_auto_expand_capability(self):
        """Test that CAPABILITY_AUTO_EXPAND is included."""
        assert 'CAPABILITY_AUTO_EXPAND' in STACK_CAPABILITIES


class TestStackInit:
    """Tests for Stack.__init__ and _load_stack_config."""

    @pytest.fixture
    def minimal_config(self, tmp_path):
        """Create a minimal valid config file."""
        template_content = """
AWSTemplateFormatVersion: '2010-09-09'
Resources:
  MyBucket:
    Type: AWS::S3::Bucket
"""
        template_path = tmp_path / 'template.yml'
        template_path.write_text(template_content)

        config = {
            'Region': 'us-west-2',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        return str(config_path)

    def test_load_minimal_config(self, minimal_config):
        """Test loading a minimal valid config."""
        stack = Stack(minimal_config)

        assert stack.region == 'us-west-2'
        assert stack.bucket == 'my-bucket'
        assert stack.stack_name == 'TestStack'
        assert stack.template.endswith('template.yml')

    def test_config_file_not_found(self, tmp_path):
        """Test error when config file doesn't exist."""
        with pytest.raises(CaricaCfnToolsError) as excinfo:
            Stack(str(tmp_path / 'nonexistent.yml'))
        assert 'not found' in str(excinfo.value)

    def test_missing_required_key_region(self, tmp_path):
        """Test error when Region is missing."""
        config = {
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        with pytest.raises(CaricaCfnToolsError) as excinfo:
            Stack(str(config_path))
        assert 'Region' in str(excinfo.value)

    def test_missing_required_key_bucket(self, tmp_path):
        """Test error when Bucket is missing."""
        config = {
            'Region': 'us-east-1',
            'Name': 'TestStack',
            'Template': 'template.yml',
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        with pytest.raises(CaricaCfnToolsError) as excinfo:
            Stack(str(config_path))
        assert 'Bucket' in str(excinfo.value)

    def test_missing_required_key_name(self, tmp_path):
        """Test error when Name is missing."""
        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Template': 'template.yml',
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        with pytest.raises(CaricaCfnToolsError) as excinfo:
            Stack(str(config_path))
        assert 'Name' in str(excinfo.value)

    def test_missing_required_key_template(self, tmp_path):
        """Test error when Template is missing."""
        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        with pytest.raises(CaricaCfnToolsError) as excinfo:
            Stack(str(config_path))
        assert 'Template' in str(excinfo.value)

    def test_template_file_not_found(self, tmp_path):
        """Test error when template file doesn't exist."""
        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'nonexistent.yml',
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        with pytest.raises(CaricaCfnToolsError) as excinfo:
            Stack(str(config_path))
        assert 'does not exist' in str(excinfo.value)

    def test_parameters_conversion(self, tmp_path):
        """Test that parameters are converted to CloudFormation format."""
        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
            'Parameters': {
                'StringParam': 'value',
                'NumberParam': 123,
            },
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        stack = Stack(str(config_path))

        assert stack.params['StringParam'] == 'value'
        assert stack.params['NumberParam'] == '123'

    def test_boolean_parameter_true(self, tmp_path):
        """Test that True boolean is converted to 'true' string."""
        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
            'Parameters': {
                'EnableFeature': True,
            },
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        stack = Stack(str(config_path))

        assert stack.params['EnableFeature'] == 'true'

    def test_boolean_parameter_false(self, tmp_path):
        """Test that False boolean is converted to 'false' string."""
        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
            'Parameters': {
                'DisableFeature': False,
            },
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        stack = Stack(str(config_path))

        assert stack.params['DisableFeature'] == 'false'

    def test_tags_from_config(self, tmp_path):
        """Test that tags are loaded from config."""
        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
            'Tags': {
                'Environment': 'dev',
                'Project': 'MyProject',
            },
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        stack = Stack(str(config_path))

        assert stack.tags == {'Environment': 'dev', 'Project': 'MyProject'}

    def test_cli_tags_override_config_tags(self, tmp_path):
        """Test that CLI tags override config file tags."""
        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
            'Tags': {
                'Environment': 'dev',
            },
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        stack = Stack(str(config_path), tags={'Environment': 'prod'})

        assert stack.tags['Environment'] == 'prod'

    def test_cli_params_override_config_params(self, tmp_path):
        """Test that CLI parameters override config file parameters."""
        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
            'Parameters': {
                'Environment': 'dev',
                'Count': '10',
            },
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        stack = Stack(str(config_path), params={'Environment': 'prod'})

        assert stack.params['Environment'] == 'prod'
        assert stack.params['Count'] == '10'

    def test_cli_params_add_new_params(self, tmp_path):
        """Test that CLI parameters can add new parameters not in config."""
        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
            'Parameters': {
                'Existing': 'value',
            },
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        stack = Stack(str(config_path), params={'NewParam': 'new-value'})

        assert stack.params['Existing'] == 'value'
        assert stack.params['NewParam'] == 'new-value'

    def test_params_empty_when_none(self, tmp_path):
        """Test that params defaults to empty dict when no config params."""
        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        stack = Stack(str(config_path))

        assert stack.params == {}

    def test_excluded_params_removes_config_params(self, tmp_path):
        """Test that excluded_params removes parameters from _params_list."""
        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
            'Parameters': {
                'Keep': 'keep-value',
                'Remove': 'remove-value',
            },
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        stack = Stack(str(config_path), excluded_params={'Remove'})

        # params dict still contains all params
        assert stack.params == {'Keep': 'keep-value', 'Remove': 'remove-value'}
        # but _params_list excludes the removed param
        params_list = {p['ParameterKey']: p['ParameterValue'] for p in stack._params_list}
        assert params_list == {'Keep': 'keep-value'}
        assert 'Remove' not in params_list

    def test_excluded_params_removes_cli_params(self, tmp_path):
        """Test that excluded_params removes CLI parameters from _params_list."""
        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        stack = Stack(str(config_path), params={'Keep': 'keep', 'Remove': 'remove'}, excluded_params={'Remove'})

        params_list = {p['ParameterKey']: p['ParameterValue'] for p in stack._params_list}
        assert params_list == {'Keep': 'keep'}
        assert 'Remove' not in params_list

    def test_excluded_params_overrides_both_config_and_cli(self, tmp_path):
        """Test that excluded_params removes params from both config and CLI in _params_list."""
        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
            'Parameters': {
                'FromConfig': 'config-value',
                'ExcludeConfig': 'will-be-removed',
            },
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        stack = Stack(
            str(config_path),
            params={'FromCli': 'cli-value', 'ExcludeCli': 'will-be-removed'},
            excluded_params={'ExcludeConfig', 'ExcludeCli'},
        )

        params_list = {p['ParameterKey']: p['ParameterValue'] for p in stack._params_list}
        assert params_list == {'FromConfig': 'config-value', 'FromCli': 'cli-value'}
        assert 'ExcludeConfig' not in params_list
        assert 'ExcludeCli' not in params_list

    def test_excluded_params_nonexistent_is_ignored(self, tmp_path):
        """Test that excluding a nonexistent parameter doesn't cause errors."""
        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
            'Parameters': {
                'Existing': 'value',
            },
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        stack = Stack(str(config_path), excluded_params={'NonExistent'})

        params_list = {p['ParameterKey']: p['ParameterValue'] for p in stack._params_list}
        assert params_list == {'Existing': 'value'}

    def test_extras_must_be_list(self, tmp_path):
        """Test that Extras must be a list."""
        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
            'Extras': {'not': 'a list'},
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        with pytest.raises(CaricaCfnToolsError) as excinfo:
            Stack(str(config_path))
        assert 'Extras' in str(excinfo.value)
        assert 'list' in str(excinfo.value)

    def test_package_extras_must_be_list(self, tmp_path):
        """Test that PackageExtras must be a list."""
        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
            'PackageExtras': 'not a list',
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        with pytest.raises(CaricaCfnToolsError) as excinfo:
            Stack(str(config_path))
        assert 'PackageExtras' in str(excinfo.value)
        assert 'list' in str(excinfo.value)

    def test_jinja_extras_must_be_list(self, tmp_path):
        """Test that JinjaExtras must be a list."""
        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
            'JinjaExtras': 123,
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        with pytest.raises(CaricaCfnToolsError) as excinfo:
            Stack(str(config_path))
        assert 'JinjaExtras' in str(excinfo.value)
        assert 'list' in str(excinfo.value)

    def test_jinja_extras_context_must_be_dict(self, tmp_path):
        """Test that JinjaExtrasContext must be a dict."""
        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
            'JinjaExtrasContext': ['not', 'a', 'dict'],
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        with pytest.raises(CaricaCfnToolsError) as excinfo:
            Stack(str(config_path))
        assert 'JinjaExtrasContext' in str(excinfo.value)
        assert 'dictionary' in str(excinfo.value)

    def test_parameters_must_be_dict(self, tmp_path):
        """Test that Parameters must be a dict."""
        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
            'Parameters': ['not', 'a', 'dict'],
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        with pytest.raises(CaricaCfnToolsError) as excinfo:
            Stack(str(config_path))
        assert 'Parameters' in str(excinfo.value)
        assert 'dictionary' in str(excinfo.value)

    def test_jinja_from_config(self, tmp_path):
        """Test that Jinja flag is loaded from config."""
        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
            'Jinja': True,
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        stack = Stack(str(config_path))

        assert stack.jinja is True

    def test_extras_combined_from_config_and_cli(self, tmp_path):
        """Test that extras from config and CLI are combined."""
        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
            'Extras': ['config_extra.txt'],
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        stack = Stack(str(config_path), extras=['cli_extra.txt'])

        assert 'config_extra.txt' in stack.extras
        assert 'cli_extra.txt' in stack.extras


class TestStackSecretsAndParameters:
    """Tests for Secrets Manager and Parameter Store loading."""

    @pytest.fixture
    def config_with_secrets(self, tmp_path):
        """Create a config with Secrets Manager parameter."""
        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
            'Parameters': {'SecretParam': {'SecretsManager': 'my-secret-id'}},
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        return str(config_path)

    @pytest.fixture
    def config_with_ssm_param(self, tmp_path):
        """Create a config with Parameter Store parameter."""
        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
            'Parameters': {'SSMParam': {'ParameterStore': '/my/param'}},
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        return str(config_path)

    @patch('carica_cfn_tools.stack_config.boto3.client')
    def test_load_secrets_manager_value(self, mock_boto_client, config_with_secrets):
        """Test loading value from Secrets Manager."""
        mock_sm = MagicMock()
        mock_sm.get_secret_value.return_value = {'SecretString': 'my-secret-value'}
        mock_boto_client.return_value = mock_sm

        stack = Stack(config_with_secrets)

        assert stack.params['SecretParam'] == 'my-secret-value'

    @patch('carica_cfn_tools.stack_config.boto3.client')
    def test_secrets_manager_error(self, mock_boto_client, config_with_secrets):
        """Test error handling for Secrets Manager failures."""
        mock_sm = MagicMock()
        mock_sm.get_secret_value.side_effect = Exception("Access denied")
        mock_boto_client.return_value = mock_sm

        with pytest.raises(CaricaCfnToolsError) as excinfo:
            Stack(config_with_secrets)
        assert 'Secrets Manager' in str(excinfo.value)
        assert 'my-secret-id' in str(excinfo.value)

    @patch('carica_cfn_tools.stack_config.boto3.client')
    def test_load_parameter_store_value(self, mock_boto_client, config_with_ssm_param):
        """Test loading value from Parameter Store."""
        mock_ssm = MagicMock()
        mock_ssm.get_parameter.return_value = {'Parameter': {'Value': 'my-ssm-value'}}
        mock_boto_client.return_value = mock_ssm

        stack = Stack(config_with_ssm_param)

        assert stack.params['SSMParam'] == 'my-ssm-value'

    @patch('carica_cfn_tools.stack_config.boto3.client')
    def test_parameter_store_error(self, mock_boto_client, config_with_ssm_param):
        """Test error handling for Parameter Store failures."""
        mock_ssm = MagicMock()
        mock_ssm.get_parameter.side_effect = Exception("Parameter not found")
        mock_boto_client.return_value = mock_ssm

        with pytest.raises(CaricaCfnToolsError) as excinfo:
            Stack(config_with_ssm_param)
        assert 'Parameter Store' in str(excinfo.value) or 'SSM' in str(excinfo.value)
        assert '/my/param' in str(excinfo.value)


class TestStackTagsList:
    """Tests for _tags_list property."""

    @pytest.fixture
    def stack_with_tags(self, tmp_path):
        """Create a stack with tags."""
        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
            'Tags': {
                'Environment': 'dev',
                'Project': 'Test',
            },
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        return Stack(str(config_path))

    def test_tags_list_format(self, stack_with_tags):
        """Test that tags are converted to CloudFormation format."""
        tags_list = stack_with_tags._tags_list

        assert isinstance(tags_list, list)
        for tag in tags_list:
            assert 'Key' in tag
            assert 'Value' in tag

    def test_tags_list_values(self, stack_with_tags):
        """Test that tag values are correct."""
        tags_list = stack_with_tags._tags_list
        tags_dict = {t['Key']: t['Value'] for t in tags_list}

        assert tags_dict['Environment'] == 'dev'
        assert tags_dict['Project'] == 'Test'


class TestStackBuildWaiterConfig:
    """Tests for _build_waiter_config method."""

    @pytest.fixture
    def stack(self, tmp_path):
        """Create a basic stack."""
        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        return Stack(str(config_path))

    def test_waiter_config_delay(self, stack):
        """Test that waiter delay is 5 seconds."""
        config = stack._build_waiter_config(100)
        assert config['Delay'] == 5

    def test_waiter_config_max_attempts(self, stack):
        """Test that MaxAttempts is calculated correctly."""
        config = stack._build_waiter_config(100)
        assert config['MaxAttempts'] == 20  # 100 / 5 = 20

    def test_waiter_config_rounds_up(self, stack):
        """Test that MaxAttempts rounds up."""
        config = stack._build_waiter_config(23)
        assert config['MaxAttempts'] == 5  # ceil(23 / 5) = 5

    def test_waiter_config_default_timeout(self, stack):
        """Test waiter config with default timeout."""
        config = stack._build_waiter_config(3600)
        assert config['MaxAttempts'] == 720  # 3600 / 5 = 720


class TestStackExpandGlobs:
    """Tests for _expand_globs method."""

    @pytest.fixture
    def stack(self, tmp_path):
        """Create a basic stack with a config in a directory with test files."""
        # Create test files
        (tmp_path / 'file1.txt').write_text('content1')
        (tmp_path / 'file2.txt').write_text('content2')
        (tmp_path / 'data.json').write_text('{}')
        subdir = tmp_path / 'subdir'
        subdir.mkdir()
        (subdir / 'nested.txt').write_text('nested')

        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        return Stack(str(config_path)), str(tmp_path)

    def test_expand_glob_pattern(self, stack):
        """Test expanding a glob pattern (rglob is recursive)."""
        stack_obj, root_path = stack
        paths = stack_obj._expand_globs(root_path, ['*.txt'])

        # rglob finds all .txt files recursively including nested ones
        assert len(paths) == 3
        assert any('file1.txt' in p for p in paths)
        assert any('file2.txt' in p for p in paths)
        assert any('nested.txt' in p for p in paths)

    def test_expand_absolute_path(self, stack):
        """Test that absolute paths pass through unchanged."""
        stack_obj, root_path = stack
        abs_path = os.path.join(root_path, 'file1.txt')
        paths = stack_obj._expand_globs(root_path, [abs_path])

        assert len(paths) == 1
        assert paths[0] == abs_path

    def test_expand_recursive_glob(self, stack):
        """Test expanding a recursive glob pattern."""
        stack_obj, root_path = stack
        paths = stack_obj._expand_globs(root_path, ['**/*.txt'])

        assert len(paths) == 3  # file1.txt, file2.txt, subdir/nested.txt
        assert any('nested.txt' in p for p in paths)

    def test_expand_nonmatching_pattern(self, stack, capsys):
        """Test warning for patterns that match nothing."""
        stack_obj, root_path = stack
        paths = stack_obj._expand_globs(root_path, ['*.nonexistent'])

        assert len(paths) == 0
        captured = capsys.readouterr()
        assert 'Warning' in captured.out
        assert 'matches nothing' in captured.out


class TestStackApplyIncludes:
    """Tests for _apply_includes method."""

    @pytest.fixture
    def stack(self, tmp_path):
        """Create a basic stack."""
        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        return Stack(str(config_path))

    def test_apply_exact_match_include(self, stack):
        """Test including a resource with an exact match."""
        template_data = {'Resources': {}, 'IncludedResources': {'MyFunction': {}}}
        included_data = {
            'Resources': {'MyFunction': {'Type': 'AWS::Lambda::Function', 'Properties': {'Runtime': 'python3.9'}}}
        }

        result = stack._apply_includes(template_data, included_data)

        assert 'MyFunction' in result['Resources']
        assert result['Resources']['MyFunction']['Type'] == 'AWS::Lambda::Function'

    def test_apply_regex_pattern_include(self, stack):
        """Test including resources with regex pattern."""
        stack.verbose = True  # Enable verbose for coverage
        template_data = {'Resources': {}, 'IncludedResources': {'MyFunction.*': {}}}
        included_data = {
            'Resources': {
                'MyFunctionHandler': {'Type': 'AWS::Lambda::Function'},
                'MyFunctionProcessor': {'Type': 'AWS::Lambda::Function'},
                'OtherResource': {'Type': 'AWS::S3::Bucket'},
            }
        }

        result = stack._apply_includes(template_data, included_data)

        # Only the first match is included (because the pattern is removed after first match)
        assert 'MyFunctionHandler' in result['Resources'] or 'MyFunctionProcessor' in result['Resources']

    def test_apply_include_merges_properties(self, stack):
        """Test that include merges properties from template."""
        template_data = {
            'Resources': {},
            'IncludedResources': {'MyFunction': {'Properties': {'Environment': {'Variables': {'KEY': 'value'}}}}},
        }
        included_data = {
            'Resources': {'MyFunction': {'Type': 'AWS::Lambda::Function', 'Properties': {'Runtime': 'python3.9'}}}
        }

        result = stack._apply_includes(template_data, included_data)

        assert result['Resources']['MyFunction']['Properties']['Runtime'] == 'python3.9'
        assert result['Resources']['MyFunction']['Properties']['Environment']['Variables']['KEY'] == 'value'

    def test_included_resources_non_dict_value_error(self, stack):
        """Test error when IncludedResources value is not a dict."""
        template_data = {'Resources': {}, 'IncludedResources': {'MyFunction': 'not a dict'}}
        included_data = {'Resources': {'MyFunction': {'Type': 'AWS::Lambda::Function'}}}

        with pytest.raises(CaricaCfnToolsError) as excinfo:
            stack._apply_includes(template_data, included_data)
        assert 'dict value' in str(excinfo.value)


class TestStackStackExists:
    """Tests for _stack_exists method."""

    @pytest.fixture
    def stack(self, tmp_path):
        """Create a basic stack."""
        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        return Stack(str(config_path))

    @patch('carica_cfn_tools.stack_config.boto3.client')
    def test_stack_exists_returns_true(self, mock_boto_client, stack):
        """Test _stack_exists returns True when stack exists."""
        mock_cfn = MagicMock()
        mock_cfn.describe_stacks.return_value = {'Stacks': [{'StackName': 'TestStack'}]}
        mock_boto_client.return_value = mock_cfn

        assert stack._stack_exists() is True

    @patch('carica_cfn_tools.stack_config.boto3.client')
    def test_stack_exists_returns_false(self, mock_boto_client, stack):
        """Test _stack_exists returns False when stack doesn't exist."""
        mock_cfn = MagicMock()
        error_response = {'Error': {'Message': 'Stack TestStack does not exist'}}
        mock_cfn.describe_stacks.side_effect = botocore.exceptions.ClientError(error_response, 'DescribeStacks')
        mock_boto_client.return_value = mock_cfn

        assert stack._stack_exists() is False

    @patch('carica_cfn_tools.stack_config.boto3.client')
    def test_stack_exists_raises_on_other_error(self, mock_boto_client, stack):
        """Test _stack_exists raises on non-existence errors."""
        mock_cfn = MagicMock()
        error_response = {'Error': {'Message': 'Access denied'}}
        mock_cfn.describe_stacks.side_effect = botocore.exceptions.ClientError(error_response, 'DescribeStacks')
        mock_boto_client.return_value = mock_cfn

        with pytest.raises(botocore.exceptions.ClientError):
            stack._stack_exists()


class TestStackApplyChangeSet:
    """Tests for apply_change_set method."""

    @pytest.fixture
    def stack(self, tmp_path):
        """Create a basic stack."""
        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        return Stack(str(config_path))

    @patch('carica_cfn_tools.stack_config.boto3.client')
    @patch.object(Stack, '_publish')
    @patch.object(Stack, '_stack_exists')
    def test_apply_change_set_create(self, mock_exists, mock_publish, mock_boto_client, stack):
        """Test creating a change set for a new stack."""
        mock_publish.return_value = 'https://s3.amazonaws.com/bucket/template.yml'
        mock_exists.return_value = False

        mock_cfn = MagicMock()
        mock_cfn.create_change_set.return_value = {'Id': 'changeset-arn', 'StackId': 'stack-arn'}
        mock_boto_client.return_value = mock_cfn

        stack.apply_change_set(
            Action.CREATE_OR_UPDATE,
            browser=False,
            wait=False,
            wait_timeout=3600,
            ignore_empty_updates=False,
            role_arn=None,
        )

        mock_cfn.create_change_set.assert_called_once()
        call_kwargs = mock_cfn.create_change_set.call_args[1]
        assert call_kwargs['ChangeSetType'] == 'CREATE'
        assert call_kwargs['StackName'] == 'TestStack'

    @patch('carica_cfn_tools.stack_config.boto3.client')
    @patch.object(Stack, '_publish')
    @patch.object(Stack, '_stack_exists')
    def test_apply_change_set_update(self, mock_exists, mock_publish, mock_boto_client, stack):
        """Test creating a change set for an existing stack."""
        mock_publish.return_value = 'https://s3.amazonaws.com/bucket/template.yml'
        mock_exists.return_value = True

        mock_cfn = MagicMock()
        mock_cfn.create_change_set.return_value = {'Id': 'changeset-arn', 'StackId': 'stack-arn'}
        mock_boto_client.return_value = mock_cfn

        stack.apply_change_set(
            Action.CREATE_OR_UPDATE,
            browser=False,
            wait=False,
            wait_timeout=3600,
            ignore_empty_updates=False,
            role_arn=None,
        )

        call_kwargs = mock_cfn.create_change_set.call_args[1]
        assert call_kwargs['ChangeSetType'] == 'UPDATE'

    @patch('carica_cfn_tools.stack_config.boto3.client')
    @patch.object(Stack, '_publish')
    @patch.object(Stack, '_stack_exists')
    def test_apply_change_set_with_role_arn(self, mock_exists, mock_publish, mock_boto_client, stack):
        """Test change set with role ARN."""
        mock_publish.return_value = 'https://s3.amazonaws.com/bucket/template.yml'
        mock_exists.return_value = False

        mock_cfn = MagicMock()
        mock_cfn.create_change_set.return_value = {'Id': 'changeset-arn', 'StackId': 'stack-arn'}
        mock_boto_client.return_value = mock_cfn

        role_arn = 'arn:aws:iam::123456789:role/CFNRole'
        stack.apply_change_set(
            Action.CREATE, browser=False, wait=False, wait_timeout=3600, ignore_empty_updates=False, role_arn=role_arn
        )

        call_kwargs = mock_cfn.create_change_set.call_args[1]
        assert call_kwargs['RoleARN'] == role_arn

    @patch('carica_cfn_tools.stack_config.boto3.client')
    @patch.object(Stack, '_publish')
    @patch.object(Stack, '_stack_exists')
    def test_apply_change_set_import_existing(self, mock_exists, mock_publish, mock_boto_client, stack):
        """Test change set with import_existing flag."""
        mock_publish.return_value = 'https://s3.amazonaws.com/bucket/template.yml'
        mock_exists.return_value = False

        mock_cfn = MagicMock()
        mock_cfn.create_change_set.return_value = {'Id': 'changeset-arn', 'StackId': 'stack-arn'}
        mock_boto_client.return_value = mock_cfn

        stack.apply_change_set(
            Action.CREATE, browser=False, wait=False, wait_timeout=3600,
            ignore_empty_updates=False, role_arn=None, import_existing=True,
        )

        call_kwargs = mock_cfn.create_change_set.call_args[1]
        assert call_kwargs['ImportExistingResources'] is True

    @patch('carica_cfn_tools.stack_config.boto3.client')
    @patch.object(Stack, '_publish')
    @patch.object(Stack, '_stack_exists')
    def test_apply_change_set_no_import_existing_by_default(self, mock_exists, mock_publish, mock_boto_client, stack):
        """Test change set does not include ImportExistingResources by default."""
        mock_publish.return_value = 'https://s3.amazonaws.com/bucket/template.yml'
        mock_exists.return_value = False

        mock_cfn = MagicMock()
        mock_cfn.create_change_set.return_value = {'Id': 'changeset-arn', 'StackId': 'stack-arn'}
        mock_boto_client.return_value = mock_cfn

        stack.apply_change_set(
            Action.CREATE_OR_UPDATE, browser=False, wait=False, wait_timeout=3600,
            ignore_empty_updates=False, role_arn=None,
        )

        call_kwargs = mock_cfn.create_change_set.call_args[1]
        assert 'ImportExistingResources' not in call_kwargs

    @patch('carica_cfn_tools.stack_config.open_url_in_browser')
    @patch('carica_cfn_tools.stack_config.boto3.client')
    @patch.object(Stack, '_publish')
    @patch.object(Stack, '_stack_exists')
    def test_apply_change_set_opens_browser(
        self, mock_exists, mock_publish, mock_boto_client, mock_open_browser, stack
    ):
        """Test change set opens browser when requested."""
        mock_publish.return_value = 'https://s3.amazonaws.com/bucket/template.yml'
        mock_exists.return_value = False

        mock_cfn = MagicMock()
        mock_cfn.create_change_set.return_value = {'Id': 'changeset-arn', 'StackId': 'stack-arn'}
        mock_boto_client.return_value = mock_cfn

        stack.apply_change_set(
            Action.CREATE, browser=True, wait=False, wait_timeout=3600, ignore_empty_updates=False, role_arn=None
        )

        mock_open_browser.assert_called_once()


class TestStackApplyStack:
    """Tests for apply_stack method."""

    @pytest.fixture
    def stack(self, tmp_path):
        """Create a basic stack."""
        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        return Stack(str(config_path))

    @patch('carica_cfn_tools.stack_config.boto3.client')
    @patch.object(Stack, '_publish')
    @patch.object(Stack, '_stack_exists')
    def test_apply_stack_create(self, mock_exists, mock_publish, mock_boto_client, stack):
        """Test creating a stack directly."""
        mock_publish.return_value = 'https://s3.amazonaws.com/bucket/template.yml'
        mock_exists.return_value = False

        mock_cfn = MagicMock()
        mock_cfn.create_stack.return_value = {'StackId': 'stack-arn'}
        mock_boto_client.return_value = mock_cfn

        stack.apply_stack(
            Action.CREATE_OR_UPDATE,
            browser=False,
            wait=False,
            wait_timeout=3600,
            ignore_empty_updates=False,
            role_arn=None,
        )

        mock_cfn.create_stack.assert_called_once()
        mock_cfn.update_stack.assert_not_called()

    @patch('carica_cfn_tools.stack_config.boto3.client')
    @patch.object(Stack, '_publish')
    @patch.object(Stack, '_stack_exists')
    def test_apply_stack_update(self, mock_exists, mock_publish, mock_boto_client, stack):
        """Test updating a stack directly."""
        mock_publish.return_value = 'https://s3.amazonaws.com/bucket/template.yml'
        mock_exists.return_value = True

        mock_cfn = MagicMock()
        mock_cfn.update_stack.return_value = {'StackId': 'stack-arn'}
        mock_boto_client.return_value = mock_cfn

        stack.apply_stack(
            Action.CREATE_OR_UPDATE,
            browser=False,
            wait=False,
            wait_timeout=3600,
            ignore_empty_updates=False,
            role_arn=None,
        )

        mock_cfn.update_stack.assert_called_once()
        mock_cfn.create_stack.assert_not_called()

    @patch('carica_cfn_tools.stack_config.boto3.client')
    @patch.object(Stack, '_publish')
    @patch.object(Stack, '_stack_exists')
    def test_apply_stack_ignore_empty_updates(self, mock_exists, mock_publish, mock_boto_client, stack, capsys):
        """Test ignoring empty updates."""
        mock_publish.return_value = 'https://s3.amazonaws.com/bucket/template.yml'
        mock_exists.return_value = True

        mock_cfn = MagicMock()
        error_response = {'Error': {'Message': 'No updates are to be performed.'}}
        mock_cfn.update_stack.side_effect = botocore.exceptions.ClientError(error_response, 'UpdateStack')
        mock_boto_client.return_value = mock_cfn

        # Should not raise when ignore_empty_updates is True
        stack.apply_stack(
            Action.UPDATE, browser=False, wait=False, wait_timeout=3600, ignore_empty_updates=True, role_arn=None
        )

        captured = capsys.readouterr()
        assert 'no changes' in captured.out.lower()

    @patch('carica_cfn_tools.stack_config.boto3.client')
    @patch.object(Stack, '_publish')
    @patch.object(Stack, '_stack_exists')
    def test_apply_stack_raise_on_empty_updates(self, mock_exists, mock_publish, mock_boto_client, stack):
        """Test raising on empty updates when not ignored."""
        mock_publish.return_value = 'https://s3.amazonaws.com/bucket/template.yml'
        mock_exists.return_value = True

        mock_cfn = MagicMock()
        error_response = {'Error': {'Message': 'No updates are to be performed.'}}
        mock_cfn.update_stack.side_effect = botocore.exceptions.ClientError(error_response, 'UpdateStack')
        mock_boto_client.return_value = mock_cfn

        with pytest.raises(CaricaCfnToolsError):
            stack.apply_stack(
                Action.UPDATE, browser=False, wait=False, wait_timeout=3600, ignore_empty_updates=False, role_arn=None
            )

    @patch('carica_cfn_tools.stack_config.open_url_in_browser')
    @patch('carica_cfn_tools.stack_config.boto3.client')
    @patch.object(Stack, '_publish')
    @patch.object(Stack, '_stack_exists')
    def test_apply_stack_opens_browser(self, mock_exists, mock_publish, mock_boto_client, mock_open_browser, stack):
        """Test stack creation opens browser when requested."""
        mock_publish.return_value = 'https://s3.amazonaws.com/bucket/template.yml'
        mock_exists.return_value = False

        mock_cfn = MagicMock()
        mock_cfn.create_stack.return_value = {'StackId': 'stack-arn'}
        mock_boto_client.return_value = mock_cfn

        stack.apply_stack(
            Action.CREATE, browser=True, wait=False, wait_timeout=3600, ignore_empty_updates=False, role_arn=None
        )

        mock_open_browser.assert_called_once()


class TestStackLoadTemplate:
    """Tests for _load_template method."""

    @pytest.fixture
    def stack_with_jinja(self, tmp_path):
        """Create a stack with Jinja enabled."""
        template_content = """
AWSTemplateFormatVersion: '2010-09-09'
Description: Template with {{ deploy_bucket }}
Resources:
  MyBucket:
    Type: AWS::S3::Bucket
"""
        template_path = tmp_path / 'template.yml'
        template_path.write_text(template_content)

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
            'Jinja': True,
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        return Stack(str(config_path))

    @pytest.fixture
    def stack_without_jinja(self, tmp_path):
        """Create a stack without Jinja."""
        template_content = """
AWSTemplateFormatVersion: '2010-09-09'
Resources:
  MyBucket:
    Type: AWS::S3::Bucket
"""
        template_path = tmp_path / 'template.yml'
        template_path.write_text(template_content)

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        return Stack(str(config_path))

    def test_load_template_without_jinja(self, stack_without_jinja):
        """Test loading a template without Jinja processing."""
        template_str, template_type, template_data = stack_without_jinja._load_template(stack_without_jinja.template)

        assert template_type == 'yaml'
        assert 'MyBucket' in template_data['Resources']

    def test_load_template_with_jinja(self, stack_with_jinja):
        """Test loading a template with Jinja processing."""
        template_str, template_type, template_data = stack_with_jinja._load_template(stack_with_jinja.template)

        assert 'my-bucket' in template_str  # Jinja replaced {{ deploy_bucket }}

    def test_load_nonexistent_template(self, stack_without_jinja):
        """Test error when template doesn't exist."""
        with pytest.raises(CaricaCfnToolsError) as excinfo:
            stack_without_jinja._load_template('/nonexistent/template.yml')
        assert 'not found' in str(excinfo.value)


class TestStackNormalizeTemplateFormat:
    """Tests for _normalize_template_format method."""

    @pytest.fixture
    def stack(self, tmp_path):
        """Create a stack with SAM conversion enabled."""
        template_path = tmp_path / 'template.yml'
        template_path.write_text('AWSTemplateFormatVersion: "2010-09-09"\nResources: {}')

        config = {
            'Region': 'us-east-1',
            'Bucket': 'my-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
        }
        config_path = tmp_path / 'config.yml'
        config_path.write_text(yaml.dump(config))

        return Stack(str(config_path), convert_sam_to_cfn=True)

    def test_non_sam_template_unchanged(self, stack):
        """Test that non-SAM templates are not modified."""
        template_data = OrderedDict(
            [
                ('AWSTemplateFormatVersion', '2010-09-09'),
                ('Resources', OrderedDict([('MyBucket', OrderedDict([('Type', 'AWS::S3::Bucket')]))])),
            ]
        )

        result = stack._normalize_template_format(template_data)

        assert result == template_data

    @patch('carica_cfn_tools.stack_config.transform')
    @patch('carica_cfn_tools.stack_config.boto3.client')
    def test_sam_template_converted(self, mock_boto_client, mock_transform, stack):
        """Test that SAM templates are converted."""
        mock_iam = MagicMock()
        mock_boto_client.return_value = mock_iam

        template_data = OrderedDict([('Transform', 'AWS::Serverless-2016-10-31'), ('Resources', OrderedDict())])

        mock_transform.return_value = OrderedDict(
            [('AWSTemplateFormatVersion', '2010-09-09'), ('Resources', OrderedDict())]
        )

        stack._normalize_template_format(template_data)

        mock_transform.assert_called_once()
