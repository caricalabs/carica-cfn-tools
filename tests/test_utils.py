"""
Unit tests for carica_cfn_tools.utils module.
"""

import json
from collections import OrderedDict
from unittest.mock import patch, MagicMock

import pytest

from carica_cfn_tools.utils import (
    get_s3_https_url,
    get_cfn_console_url_changeset,
    get_cfn_console_url_stack,
    open_url_in_browser,
    update_dict,
    dict_find_path,
    copy_dict,
    load_cfn_template,
    dump_cfn_template_yaml,
    dump_cfn_template_json,
)


class TestGetS3HttpsUrl:
    """Tests for get_s3_https_url function."""

    def test_us_east_1_region(self):
        """us-east-1 should use 's3' without region suffix."""
        url = get_s3_https_url('us-east-1', 'my-bucket', 'path/to/key.txt')
        assert url == 'https://s3.amazonaws.com/my-bucket/path/to/key.txt'

    def test_other_region(self):
        """Other regions should include region in hostname."""
        url = get_s3_https_url('us-west-2', 'my-bucket', 'path/to/key.txt')
        assert url == 'https://s3-us-west-2.amazonaws.com/my-bucket/path/to/key.txt'

    def test_eu_region(self):
        """EU regions should include region in hostname."""
        url = get_s3_https_url('eu-west-1', 'my-bucket', 'file.yml')
        assert url == 'https://s3-eu-west-1.amazonaws.com/my-bucket/file.yml'

    def test_key_with_special_chars(self):
        """Keys with special characters are preserved (not URL encoded here)."""
        url = get_s3_https_url('us-east-1', 'bucket', 'path/with spaces/file.txt')
        assert url == 'https://s3.amazonaws.com/bucket/path/with spaces/file.txt'


class TestGetCfnConsoleUrlChangeset:
    """Tests for get_cfn_console_url_changeset function."""

    def test_basic_url_generation(self):
        """Test basic change set URL generation."""
        url = get_cfn_console_url_changeset(
            'us-east-1',
            'arn:aws:cloudformation:us-east-1:123456789:stack/MyStack/abc123',
            'arn:aws:cloudformation:us-east-1:123456789:changeSet/MyChangeSet/def456',
        )
        assert 'region=us-east-1' in url
        assert 'console.aws.amazon.com/cloudformation/home' in url
        assert 'changesets/changes' in url
        # ARNs should be URL encoded
        assert '%3A' in url  # encoded colon
        assert '%2F' in url  # encoded slash

    def test_url_encoding_of_arns(self):
        """Verify that slashes and colons in ARNs are properly encoded."""
        url = get_cfn_console_url_changeset(
            'us-west-2',
            'arn:aws:cloudformation:us-west-2:111:stack/Stack/id',
            'arn:aws:cloudformation:us-west-2:111:changeSet/Change/id',
        )
        # Should not contain unencoded slashes in the ARN portions (after the #)
        fragment = url.split('#')[1]
        assert 'arn%3Aaws%3Acloudformation' in fragment


class TestGetCfnConsoleUrlStack:
    """Tests for get_cfn_console_url_stack function."""

    def test_basic_url_generation(self):
        """Test basic stack URL generation."""
        url = get_cfn_console_url_stack('us-east-1', 'arn:aws:cloudformation:us-east-1:123456789:stack/MyStack/abc123')
        assert 'region=us-east-1' in url
        assert 'console.aws.amazon.com/cloudformation/home' in url
        assert 'stackinfo' in url
        # ARN should be URL encoded
        assert '%3A' in url
        assert '%2F' in url


class TestOpenUrlInBrowser:
    """Tests for open_url_in_browser function."""

    @patch('carica_cfn_tools.utils.subprocess.Popen')
    @patch('carica_cfn_tools.utils.sys.platform', 'darwin')
    def test_macos_uses_open_command(self, mock_popen):
        """macOS should use 'open' command."""
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc

        open_url_in_browser('https://example.com')

        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert args[0] == 'open'
        assert args[1] == 'https://example.com'

    @patch('carica_cfn_tools.utils.subprocess.Popen')
    @patch('carica_cfn_tools.utils.sys.platform', 'linux')
    def test_linux_uses_xdg_open(self, mock_popen):
        """Linux should use 'xdg-open' command."""
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc

        open_url_in_browser('https://example.com')

        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert args[0] == 'xdg-open'
        assert args[1] == 'https://example.com'

    @patch('carica_cfn_tools.utils.subprocess.Popen')
    def test_exception_is_silently_handled(self, mock_popen):
        """Exceptions should be silently caught."""
        mock_popen.side_effect = OSError("Command not found")

        # Should not raise
        open_url_in_browser('https://example.com')


class TestUpdateDict:
    """Tests for update_dict function."""

    def test_simple_update(self):
        """Test simple key update."""
        d = {'a': 1, 'b': 2}
        u = {'b': 3, 'c': 4}
        result = update_dict(d, u)
        assert result == {'a': 1, 'b': 3, 'c': 4}

    def test_nested_update(self):
        """Test nested dictionary update."""
        d = {'a': {'x': 1, 'y': 2}}
        u = {'a': {'y': 3, 'z': 4}}
        result = update_dict(d, u)
        assert result == {'a': {'x': 1, 'y': 3, 'z': 4}}

    def test_deep_nested_update(self):
        """Test deeply nested dictionary update."""
        d = {'a': {'b': {'c': 1}}}
        u = {'a': {'b': {'d': 2}}}
        result = update_dict(d, u)
        assert result == {'a': {'b': {'c': 1, 'd': 2}}}

    def test_non_dict_source_returns_update(self):
        """When source is not a dict, return the update value."""
        result = update_dict('not a dict', {'a': 1})
        assert result == {'a': 1}

    def test_overwrite_non_dict_with_dict(self):
        """Overwriting non-dict with dict should replace."""
        d = {'a': 1}
        u = {'a': {'nested': 'value'}}
        result = update_dict(d, u)
        assert result == {'a': {'nested': 'value'}}

    def test_overwrite_dict_with_non_dict(self):
        """Overwriting dict with non-dict should replace."""
        d = {'a': {'nested': 'value'}}
        u = {'a': 1}
        result = update_dict(d, u)
        assert result == {'a': 1}

    def test_empty_update(self):
        """Empty update dict should not change source."""
        d = {'a': 1, 'b': 2}
        result = update_dict(d, {})
        assert result == {'a': 1, 'b': 2}

    def test_empty_source(self):
        """Empty source should be populated by update."""
        result = update_dict({}, {'a': 1})
        assert result == {'a': 1}


class TestDictFindPath:
    """Tests for dict_find_path function."""

    def test_simple_path(self, sample_nested_dict):
        """Test finding a top-level key."""
        assert dict_find_path(sample_nested_dict, 'foo') == 123

    def test_nested_path(self, sample_nested_dict):
        """Test finding a nested key."""
        assert dict_find_path(sample_nested_dict, 'bar.color') == 'red'

    def test_deep_nested_path(self, sample_nested_dict):
        """Test finding a deeply nested key."""
        assert dict_find_path(sample_nested_dict, 'bar.nested.deep') == 'value'

    def test_custom_separator(self, sample_nested_dict):
        """Test using a custom path separator."""
        assert dict_find_path(sample_nested_dict, 'bar|color', path_sep='|') == 'red'

    def test_not_found_returns_default(self, sample_nested_dict):
        """Test that missing path returns default."""
        assert dict_find_path(sample_nested_dict, 'missing.path') is None
        assert dict_find_path(sample_nested_dict, 'missing.path', default='not found') == 'not found'

    def test_partial_path_not_found(self, sample_nested_dict):
        """Test partial path that doesn't fully resolve."""
        assert dict_find_path(sample_nested_dict, 'bar.missing') is None

    def test_path_through_non_dict(self, sample_nested_dict):
        """Test path that tries to traverse through a non-dict."""
        assert dict_find_path(sample_nested_dict, 'foo.bar') is None

    def test_empty_path(self, sample_nested_dict):
        """Test empty path returns the top level dict."""
        result = dict_find_path(sample_nested_dict, '')
        # Empty string split gives [''], which would try to find '' key
        assert result is None

    def test_single_key_path(self):
        """Test single key without separator."""
        d = {'key': 'value'}
        assert dict_find_path(d, 'key') == 'value'


class TestCopyDict:
    """Tests for copy_dict function."""

    def test_simple_dict_copy(self):
        """Test copying a simple dictionary."""
        original = {'a': 1, 'b': 2}
        copied = copy_dict(original)
        assert copied == original
        assert copied is not original

    def test_nested_dict_copy(self):
        """Test copying nested dictionaries."""
        original = {'a': {'b': {'c': 1}}}
        copied = copy_dict(original)
        assert copied == original
        assert copied['a'] is not original['a']
        assert copied['a']['b'] is not original['a']['b']

    def test_list_copy(self):
        """Test copying lists within dicts."""
        original = {'items': [1, 2, 3]}
        copied = copy_dict(original)
        assert copied == original
        assert copied['items'] is not original['items']

    def test_nested_list_of_dicts(self):
        """Test copying lists containing dictionaries."""
        original = {'items': [{'a': 1}, {'b': 2}]}
        copied = copy_dict(original)
        assert copied == original
        assert copied['items'][0] is not original['items'][0]

    def test_custom_impl(self):
        """Test using custom dict implementation."""
        original = {'a': 1, 'b': {'c': 2}}
        copied = copy_dict(original, impl=OrderedDict)
        assert isinstance(copied, OrderedDict)
        assert isinstance(copied['b'], OrderedDict)

    def test_tuple_handling(self):
        """Test that tuples are handled (returns generator)."""
        original = {'items': (1, 2, 3)}
        copied = copy_dict(original)
        # The tuple becomes a generator, so we need to consume it
        assert 'items' in copied

    def test_scalar_passthrough(self):
        """Test that scalars are passed through unchanged."""
        assert copy_dict(42) == 42
        assert copy_dict('string') == 'string'
        assert copy_dict(None) is None


class TestLoadCfnTemplate:
    """Tests for load_cfn_template function."""

    def test_load_yaml_template(self, sample_yaml_template):
        """Test loading a YAML template."""
        data, template_type = load_cfn_template(sample_yaml_template)
        assert template_type == 'yaml'
        assert data['AWSTemplateFormatVersion'] == '2010-09-09'
        assert 'Resources' in data
        assert 'MyBucket' in data['Resources']

    def test_load_json_template(self, sample_json_template):
        """Test loading a JSON template."""
        data, template_type = load_cfn_template(sample_json_template)
        assert template_type == 'json'
        assert data['AWSTemplateFormatVersion'] == '2010-09-09'
        assert 'Resources' in data
        assert 'MyBucket' in data['Resources']

    def test_returns_ordered_dict(self, sample_yaml_template):
        """Test that result is an OrderedDict."""
        data, _ = load_cfn_template(sample_yaml_template)
        assert isinstance(data, OrderedDict)

    def test_invalid_template_raises_error(self):
        """Test that invalid template raises ValueError."""
        with pytest.raises(ValueError) as excinfo:
            load_cfn_template('not valid json or yaml: {{{{')
        assert 'Could not read template as JSON or YAML' in str(excinfo.value)

    def test_empty_yaml_template(self):
        """Test loading an empty YAML template."""
        data, template_type = load_cfn_template('{}')
        assert template_type == 'json'
        assert data == {}

    def test_complex_yaml_with_intrinsic_functions(self):
        """Test loading YAML with CloudFormation intrinsic functions."""
        template = """
AWSTemplateFormatVersion: '2010-09-09'
Resources:
  MyBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: !Sub ${AWS::StackName}-bucket
"""
        data, template_type = load_cfn_template(template)
        assert template_type == 'yaml'
        assert 'Resources' in data


class TestDumpCfnTemplateYaml:
    """Tests for dump_cfn_template_yaml function."""

    def test_dump_dict_to_yaml(self):
        """Test dumping a dict to YAML format."""
        template_data = OrderedDict(
            [
                ('AWSTemplateFormatVersion', '2010-09-09'),
                ('Resources', OrderedDict([('MyBucket', OrderedDict([('Type', 'AWS::S3::Bucket')]))])),
            ]
        )
        result = dump_cfn_template_yaml(template_data)
        assert 'AWSTemplateFormatVersion' in result
        assert 'MyBucket' in result
        assert 'AWS::S3::Bucket' in result

    def test_dump_preserves_structure(self, sample_yaml_template):
        """Test that dump/load roundtrip preserves structure."""
        data, _ = load_cfn_template(sample_yaml_template)
        yaml_output = dump_cfn_template_yaml(data)
        reloaded, _ = load_cfn_template(yaml_output)
        assert reloaded['AWSTemplateFormatVersion'] == data['AWSTemplateFormatVersion']
        assert 'MyBucket' in reloaded['Resources']


class TestDumpCfnTemplateJson:
    """Tests for dump_cfn_template_json function."""

    def test_dump_dict_to_json(self):
        """Test dumping a dict to JSON format."""
        template_data = OrderedDict(
            [
                ('AWSTemplateFormatVersion', '2010-09-09'),
                ('Resources', OrderedDict([('MyBucket', OrderedDict([('Type', 'AWS::S3::Bucket')]))])),
            ]
        )
        result = dump_cfn_template_json(template_data)
        # Verify it's valid JSON
        parsed = json.loads(result)
        assert parsed['AWSTemplateFormatVersion'] == '2010-09-09'
        assert 'MyBucket' in parsed['Resources']

    def test_dump_preserves_structure(self, sample_json_template):
        """Test that dump/load roundtrip preserves structure."""
        data, _ = load_cfn_template(sample_json_template)
        json_output = dump_cfn_template_json(data)
        reloaded, _ = load_cfn_template(json_output)
        assert reloaded['AWSTemplateFormatVersion'] == data['AWSTemplateFormatVersion']
        assert 'MyBucket' in reloaded['Resources']
