"""
Unit tests for carica_cfn_tools.cli module.
"""

from unittest.mock import patch, MagicMock

import pytest
import yaml
from click import BadParameter
from click.testing import CliRunner

from carica_cfn_tools.cli import (
    ActionParamType,
    parse_tags,
    parse_parameters,
    cli,
)
from carica_cfn_tools.stack_config import Action


class TestActionParamType:
    """Tests for ActionParamType class."""

    def test_choices_include_all_actions(self):
        """Test that all Action enum values are valid choices."""
        param_type = ActionParamType()
        assert 'create' in param_type.choices
        assert 'update' in param_type.choices
        assert 'create_or_update' in param_type.choices

    def test_convert_string_to_action(self):
        """Test converting string values to Action enum."""
        param_type = ActionParamType()
        assert param_type.convert('create', None, None) == Action.CREATE
        assert param_type.convert('update', None, None) == Action.UPDATE
        assert param_type.convert('create_or_update', None, None) == Action.CREATE_OR_UPDATE

    def test_convert_action_passthrough(self):
        """Test that Action values pass through unchanged."""
        param_type = ActionParamType()
        assert param_type.convert(Action.CREATE, None, None) == Action.CREATE
        assert param_type.convert(Action.UPDATE, None, None) == Action.UPDATE

    def test_invalid_action_raises_error(self):
        """Test that invalid action values raise an error."""
        param_type = ActionParamType()
        # Click.Choice raises BadParameter for invalid values (ctx must be None)
        from click import BadParameter

        with pytest.raises(BadParameter):
            param_type.convert('invalid', None, None)


class TestParseTags:
    """Tests for parse_tags function."""

    def test_single_tag(self):
        """Test parsing a single tag."""
        result = parse_tags(['key=value'])
        assert result == {'key': 'value'}

    def test_multiple_tags(self):
        """Test parsing multiple tags."""
        result = parse_tags(['key1=value1', 'key2=value2'])
        assert result == {'key1': 'value1', 'key2': 'value2'}

    def test_tag_with_equals_in_value(self):
        """Test tag where value contains equals sign."""
        result = parse_tags(['key=value=with=equals'])
        assert result == {'key': 'value=with=equals'}

    def test_empty_tags(self):
        """Test parsing empty tag list."""
        result = parse_tags([])
        assert result == {}

    def test_tag_with_special_characters(self):
        """Test tag with special characters in value."""
        result = parse_tags(['env=prod-us-east-1', 'url=https://example.com'])
        assert result == {'env': 'prod-us-east-1', 'url': 'https://example.com'}

    def test_missing_equals_raises_error(self):
        """Test that tag without equals raises BadParameter."""
        with pytest.raises(BadParameter) as excinfo:
            parse_tags(['invalid-tag'])
        assert 'must be formatted like "key=value"' in str(excinfo.value)

    def test_empty_key_raises_error(self):
        """Test that empty key raises BadParameter."""
        with pytest.raises(BadParameter):
            parse_tags(['=value'])

    def test_empty_value_raises_error(self):
        """Test that empty value raises BadParameter."""
        with pytest.raises(BadParameter):
            parse_tags(['key='])


class TestParseParameters:
    """Tests for parse_parameters function."""

    def test_single_parameter(self):
        """Test parsing a single parameter."""
        result = parse_parameters(['key=value'])
        assert result == {'key': 'value'}

    def test_multiple_parameters(self):
        """Test parsing multiple parameters."""
        result = parse_parameters(['key1=value1', 'key2=value2'])
        assert result == {'key1': 'value1', 'key2': 'value2'}

    def test_parameter_with_equals_in_value(self):
        """Test parameter where value contains equals sign."""
        result = parse_parameters(['key=value=with=equals'])
        assert result == {'key': 'value=with=equals'}

    def test_empty_parameters(self):
        """Test parsing empty parameter list."""
        result = parse_parameters([])
        assert result == {}

    def test_parameter_with_special_characters(self):
        """Test parameter with special characters in value."""
        result = parse_parameters(['env=prod-us-east-1', 'url=https://example.com'])
        assert result == {'env': 'prod-us-east-1', 'url': 'https://example.com'}

    def test_missing_equals_raises_error(self):
        """Test that parameter without equals raises BadParameter."""
        with pytest.raises(BadParameter) as excinfo:
            parse_parameters(['invalid-param'])
        assert 'must be formatted like "key=value"' in str(excinfo.value)

    def test_empty_key_raises_error(self):
        """Test that empty key raises BadParameter."""
        with pytest.raises(BadParameter):
            parse_parameters(['=value'])

    def test_empty_value_raises_error(self):
        """Test that empty value raises BadParameter."""
        with pytest.raises(BadParameter):
            parse_parameters(['key='])

    def test_parameter_with_multiple_equals(self):
        """Test parameter with multiple equals signs in value."""
        result = parse_parameters(['key=a=b=c=d'])
        assert result == {'key': 'a=b=c=d'}

    def test_parameter_value_starts_with_equals(self):
        """Test parameter where value starts with equals."""
        result = parse_parameters(['key==value'])
        assert result == {'key': '=value'}

    def test_parameter_value_ends_with_equals(self):
        """Test parameter where value ends with equals."""
        result = parse_parameters(['key=value='])
        assert result == {'key': 'value='}

    def test_parameter_value_is_only_equals(self):
        """Test parameter where value is only equals signs."""
        result = parse_parameters(['key===='])
        assert result == {'key': '==='}

    def test_parameter_with_base64_value(self):
        """Test parameter with base64-encoded value (single padding)."""
        result = parse_parameters(['Secret=dGVzdCBzZWNyZXQ='])
        assert result == {'Secret': 'dGVzdCBzZWNyZXQ='}

    def test_parameter_with_base64_double_padding(self):
        """Test parameter with base64-encoded value (double padding)."""
        result = parse_parameters(['Secret=dGVzdA=='])
        assert result == {'Secret': 'dGVzdA=='}


class TestCli:
    """Integration tests for the CLI command."""

    @pytest.fixture
    def runner(self):
        """Create a CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def valid_config_file(self, tmp_path):
        """Create a valid config file for testing."""
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
            'Bucket': 'my-cfn-bucket',
            'Name': 'TestStack',
            'Template': 'template.yml',
        }
        config_path = tmp_path / 'stack-config.yml'
        config_path.write_text(yaml.dump(config))

        return str(config_path)

    def test_version_option(self, runner):
        """Test --version option shows version."""
        result = runner.invoke(cli, ['--version'])
        assert result.exit_code == 0
        assert 'version' in result.output.lower() or '.' in result.output

    def test_missing_config_file(self, runner):
        """Test error when config file doesn't exist."""
        result = runner.invoke(cli, ['/nonexistent/config.yml'])
        assert result.exit_code == 1
        assert 'not found' in result.output.lower() or 'error' in result.output.lower()

    @patch('carica_cfn_tools.cli.Stack')
    def test_query_option(self, mock_stack_class, runner, valid_config_file):
        """Test --query option prints config value."""
        mock_stack = MagicMock()
        mock_stack.raw_config = {'Region': 'us-east-1', 'Parameters': {'MyParam': 'MyValue'}}
        mock_stack_class.return_value = mock_stack

        result = runner.invoke(cli, [valid_config_file, '--query', 'Region'])
        assert result.exit_code == 0
        assert 'us-east-1' in result.output

    @patch('carica_cfn_tools.cli.Stack')
    def test_query_nested_value(self, mock_stack_class, runner, valid_config_file):
        """Test --query with nested path."""
        mock_stack = MagicMock()
        mock_stack.raw_config = {'Parameters': {'MyParam': 'MyValue'}}
        mock_stack_class.return_value = mock_stack

        result = runner.invoke(cli, [valid_config_file, '--query', 'Parameters.MyParam'])
        assert result.exit_code == 0
        assert 'MyValue' in result.output

    @patch('carica_cfn_tools.cli.Stack')
    def test_query_not_found(self, mock_stack_class, runner, valid_config_file):
        """Test --query with non-existent key."""
        mock_stack = MagicMock()
        mock_stack.raw_config = {'Region': 'us-east-1'}
        mock_stack_class.return_value = mock_stack

        result = runner.invoke(cli, [valid_config_file, '--query', 'NonExistent'])
        assert result.exit_code == 1
        assert 'not found' in result.output.lower()

    @patch('carica_cfn_tools.cli.Stack')
    def test_direct_flag_calls_apply_stack(self, mock_stack_class, runner, valid_config_file):
        """Test --direct flag calls apply_stack method."""
        mock_stack = MagicMock()
        mock_stack_class.return_value = mock_stack

        result = runner.invoke(cli, [valid_config_file, '--direct'])

        mock_stack.apply_stack.assert_called_once()
        mock_stack.apply_change_set.assert_not_called()

    @patch('carica_cfn_tools.cli.Stack')
    def test_default_calls_apply_change_set(self, mock_stack_class, runner, valid_config_file):
        """Test default (no --direct) calls apply_change_set method."""
        mock_stack = MagicMock()
        mock_stack_class.return_value = mock_stack

        result = runner.invoke(cli, [valid_config_file])

        mock_stack.apply_change_set.assert_called_once()
        mock_stack.apply_stack.assert_not_called()

    @patch('carica_cfn_tools.cli.Stack')
    def test_action_option(self, mock_stack_class, runner, valid_config_file):
        """Test --action option is passed to Stack methods."""
        mock_stack = MagicMock()
        mock_stack_class.return_value = mock_stack

        result = runner.invoke(cli, [valid_config_file, '--action', 'create'])

        call_args = mock_stack.apply_change_set.call_args
        assert call_args[0][0] == Action.CREATE

    @patch('carica_cfn_tools.cli.Stack')
    def test_browser_flag(self, mock_stack_class, runner, valid_config_file):
        """Test --browser flag is passed through."""
        mock_stack = MagicMock()
        mock_stack_class.return_value = mock_stack

        result = runner.invoke(cli, [valid_config_file, '--browser'])

        call_args = mock_stack.apply_change_set.call_args
        assert call_args[0][1] is True  # browser argument

    @patch('carica_cfn_tools.cli.Stack')
    def test_wait_flag(self, mock_stack_class, runner, valid_config_file):
        """Test --wait flag is passed through."""
        mock_stack = MagicMock()
        mock_stack_class.return_value = mock_stack

        result = runner.invoke(cli, [valid_config_file, '--wait'])

        call_args = mock_stack.apply_change_set.call_args
        assert call_args[0][2] is True  # wait argument

    @patch('carica_cfn_tools.cli.Stack')
    def test_wait_timeout_option(self, mock_stack_class, runner, valid_config_file):
        """Test --wait-timeout option."""
        mock_stack = MagicMock()
        mock_stack_class.return_value = mock_stack

        result = runner.invoke(cli, [valid_config_file, '--wait-timeout', '7200'])

        call_args = mock_stack.apply_change_set.call_args
        assert call_args[0][3] == 7200  # wait_timeout argument

    @patch('carica_cfn_tools.cli.Stack')
    def test_default_wait_timeout(self, mock_stack_class, runner, valid_config_file):
        """Test default wait timeout is 3600."""
        mock_stack = MagicMock()
        mock_stack_class.return_value = mock_stack

        result = runner.invoke(cli, [valid_config_file])

        call_args = mock_stack.apply_change_set.call_args
        assert call_args[0][3] == 3600  # wait_timeout argument

    @patch('carica_cfn_tools.cli.Stack')
    def test_ignore_empty_updates_flag(self, mock_stack_class, runner, valid_config_file):
        """Test --ignore-empty-updates flag."""
        mock_stack = MagicMock()
        mock_stack_class.return_value = mock_stack

        result = runner.invoke(cli, [valid_config_file, '--ignore-empty-updates'])

        call_args = mock_stack.apply_change_set.call_args
        assert call_args[0][4] is True  # ignore_empty_updates argument

    @patch('carica_cfn_tools.cli.Stack')
    def test_role_arn_option(self, mock_stack_class, runner, valid_config_file):
        """Test --role-arn option."""
        mock_stack = MagicMock()
        mock_stack_class.return_value = mock_stack

        role_arn = 'arn:aws:iam::123456789:role/CFNRole'
        result = runner.invoke(cli, [valid_config_file, '--role-arn', role_arn])

        call_args = mock_stack.apply_change_set.call_args
        assert call_args[0][5] == role_arn  # role_arn argument

    @patch('carica_cfn_tools.cli.Stack')
    def test_include_template_option(self, mock_stack_class, runner, valid_config_file):
        """Test --include-template option is passed to Stack constructor."""
        mock_stack = MagicMock()
        mock_stack_class.return_value = mock_stack

        result = runner.invoke(
            cli, [valid_config_file, '--include-template', 'inc1.yml', '--include-template', 'inc2.yml']
        )

        call_args = mock_stack_class.call_args
        assert 'inc1.yml' in call_args[0][1]
        assert 'inc2.yml' in call_args[0][1]

    @patch('carica_cfn_tools.cli.Stack')
    def test_extra_option(self, mock_stack_class, runner, valid_config_file):
        """Test --extra option is passed to Stack constructor."""
        mock_stack = MagicMock()
        mock_stack_class.return_value = mock_stack

        result = runner.invoke(cli, [valid_config_file, '--extra', '*.txt', '--extra', '*.json'])

        call_args = mock_stack_class.call_args
        assert '*.txt' in call_args[0][3]
        assert '*.json' in call_args[0][3]

    @patch('carica_cfn_tools.cli.Stack')
    def test_jinja_flag(self, mock_stack_class, runner, valid_config_file):
        """Test --jinja flag is passed to Stack constructor."""
        mock_stack = MagicMock()
        mock_stack_class.return_value = mock_stack

        result = runner.invoke(cli, [valid_config_file, '--jinja'])

        call_args = mock_stack_class.call_args
        assert call_args[0][4] is True  # jinja argument

    @patch('carica_cfn_tools.cli.Stack')
    def test_tag_option(self, mock_stack_class, runner, valid_config_file):
        """Test --tag option is passed to Stack constructor."""
        mock_stack = MagicMock()
        mock_stack_class.return_value = mock_stack

        result = runner.invoke(cli, [valid_config_file, '--tag', 'env=prod', '--tag', 'team=platform'])

        call_args = mock_stack_class.call_args
        tags = call_args[0][8]  # tags is position 8 (0-indexed)
        assert tags == {'env': 'prod', 'team': 'platform'}

    @patch('carica_cfn_tools.cli.Stack')
    def test_parameter_option(self, mock_stack_class, runner, valid_config_file):
        """Test --parameter option is passed to Stack constructor."""
        mock_stack = MagicMock()
        mock_stack_class.return_value = mock_stack

        result = runner.invoke(
            cli, [valid_config_file, '--parameter', 'Env=prod', '--parameter', 'Count=5']
        )

        call_args = mock_stack_class.call_args
        params = call_args[0][9]  # params is position 9 (0-indexed)
        assert params == {'Env': 'prod', 'Count': '5'}

    def test_invalid_parameter_format(self, runner, valid_config_file):
        """Test that invalid parameter format shows error."""
        result = runner.invoke(cli, [valid_config_file, '--parameter', 'invalid'])
        assert result.exit_code != 0

    @patch('carica_cfn_tools.cli.Stack')
    def test_tag_with_equals_in_value(self, mock_stack_class, runner, valid_config_file):
        """Test --tag with equals signs in the value."""
        mock_stack = MagicMock()
        mock_stack_class.return_value = mock_stack

        result = runner.invoke(cli, [valid_config_file, '--tag', 'config=key=value'])

        call_args = mock_stack_class.call_args
        tags = call_args[0][8]
        assert tags == {'config': 'key=value'}

    @patch('carica_cfn_tools.cli.Stack')
    def test_tag_with_base64_value(self, mock_stack_class, runner, valid_config_file):
        """Test --tag with base64-encoded value containing equals padding."""
        mock_stack = MagicMock()
        mock_stack_class.return_value = mock_stack

        result = runner.invoke(cli, [valid_config_file, '--tag', 'secret=dGVzdA=='])

        call_args = mock_stack_class.call_args
        tags = call_args[0][8]
        assert tags == {'secret': 'dGVzdA=='}

    @patch('carica_cfn_tools.cli.Stack')
    def test_parameter_with_equals_in_value(self, mock_stack_class, runner, valid_config_file):
        """Test --parameter with equals signs in the value."""
        mock_stack = MagicMock()
        mock_stack_class.return_value = mock_stack

        result = runner.invoke(cli, [valid_config_file, '--parameter', 'ConnectionString=host=db;user=admin'])

        call_args = mock_stack_class.call_args
        params = call_args[0][9]
        assert params == {'ConnectionString': 'host=db;user=admin'}

    @patch('carica_cfn_tools.cli.Stack')
    def test_parameter_with_base64_value(self, mock_stack_class, runner, valid_config_file):
        """Test --parameter with base64-encoded value containing equals padding."""
        mock_stack = MagicMock()
        mock_stack_class.return_value = mock_stack

        result = runner.invoke(cli, [valid_config_file, '--parameter', 'EncodedData=SGVsbG8gV29ybGQh'])

        call_args = mock_stack_class.call_args
        params = call_args[0][9]
        assert params == {'EncodedData': 'SGVsbG8gV29ybGQh'}

    @patch('carica_cfn_tools.cli.Stack')
    def test_multiple_tags_with_equals(self, mock_stack_class, runner, valid_config_file):
        """Test multiple --tag options with equals signs in values."""
        mock_stack = MagicMock()
        mock_stack_class.return_value = mock_stack

        result = runner.invoke(
            cli,
            [valid_config_file, '--tag', 'eq1=a=b', '--tag', 'eq2=c=d=e'],
        )

        call_args = mock_stack_class.call_args
        tags = call_args[0][8]
        assert tags == {'eq1': 'a=b', 'eq2': 'c=d=e'}

    @patch('carica_cfn_tools.cli.Stack')
    def test_multiple_parameters_with_equals(self, mock_stack_class, runner, valid_config_file):
        """Test multiple --parameter options with equals signs in values."""
        mock_stack = MagicMock()
        mock_stack_class.return_value = mock_stack

        result = runner.invoke(
            cli,
            [valid_config_file, '--parameter', 'Param1=x=y', '--parameter', 'Param2=a=b=c'],
        )

        call_args = mock_stack_class.call_args
        params = call_args[0][9]
        assert params == {'Param1': 'x=y', 'Param2': 'a=b=c'}

    @patch('carica_cfn_tools.cli.Stack')
    def test_verbose_flag(self, mock_stack_class, runner, valid_config_file):
        """Test --verbose flag is passed to Stack constructor."""
        mock_stack = MagicMock()
        mock_stack_class.return_value = mock_stack

        result = runner.invoke(cli, [valid_config_file, '--verbose'])

        call_args = mock_stack_class.call_args
        assert call_args[0][7] is True  # verbose is position 7 (0-indexed)

    @patch('carica_cfn_tools.cli.Stack')
    def test_sam_to_cfn_default_true(self, mock_stack_class, runner, valid_config_file):
        """Test --sam-to-cfn is True by default."""
        mock_stack = MagicMock()
        mock_stack_class.return_value = mock_stack

        result = runner.invoke(cli, [valid_config_file])

        call_args = mock_stack_class.call_args
        assert call_args[0][2] is True  # convert_sam_to_cfn argument

    @patch('carica_cfn_tools.cli.Stack')
    def test_no_sam_to_cfn_flag(self, mock_stack_class, runner, valid_config_file):
        """Test --no-sam-to-cfn flag."""
        mock_stack = MagicMock()
        mock_stack_class.return_value = mock_stack

        result = runner.invoke(cli, [valid_config_file, '--no-sam-to-cfn'])

        call_args = mock_stack_class.call_args
        assert call_args[0][2] is False  # convert_sam_to_cfn argument

    def test_invalid_tag_format(self, runner, valid_config_file):
        """Test that invalid tag format shows error."""
        result = runner.invoke(cli, [valid_config_file, '--tag', 'invalid'])
        assert result.exit_code != 0


class TestCliHelp:
    """Tests for CLI help text."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_help_option(self, runner):
        """Test --help option shows help."""
        result = runner.invoke(cli, ['--help'])
        assert result.exit_code == 0
        assert 'STACK_CONFIG' in result.output
        assert '--action' in result.output
        assert '--browser' in result.output
        assert '--direct' in result.output
        assert '--wait' in result.output

    def test_help_shows_action_choices(self, runner):
        """Test help shows valid action choices."""
        result = runner.invoke(cli, ['--help'])
        assert 'create' in result.output
        assert 'update' in result.output
        assert 'create_or_update' in result.output
