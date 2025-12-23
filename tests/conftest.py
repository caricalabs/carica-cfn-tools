"""
Pytest fixtures for carica_cfn_tools tests.
"""

import os
import tempfile
import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_yaml_template():
    """Sample CloudFormation YAML template."""
    return """
AWSTemplateFormatVersion: '2010-09-09'
Description: Sample template
Resources:
  MyBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: my-test-bucket
Outputs:
  BucketName:
    Value: !Ref MyBucket
"""


@pytest.fixture
def sample_json_template():
    """Sample CloudFormation JSON template."""
    return """{
  "AWSTemplateFormatVersion": "2010-09-09",
  "Description": "Sample template",
  "Resources": {
    "MyBucket": {
      "Type": "AWS::S3::Bucket",
      "Properties": {
        "BucketName": "my-test-bucket"
      }
    }
  },
  "Outputs": {
    "BucketName": {
      "Value": {"Ref": "MyBucket"}
    }
  }
}"""


@pytest.fixture
def sample_sam_template():
    """Sample SAM template."""
    return """
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: Sample SAM template
Resources:
  HelloFunction:
    Type: AWS::Serverless::Function
    Properties:
      Handler: index.handler
      Runtime: python3.9
      CodeUri: ./code
"""


@pytest.fixture
def sample_stack_config():
    """Sample stack configuration dictionary."""
    return {
        'Region': 'us-east-1',
        'Bucket': 'my-cfn-bucket',
        'Name': 'TestStack',
        'Template': 'template.yml',
        'Parameters': {
            'Environment': 'dev',
            'EnableFeature': True,
            'DisableOther': False,
        },
        'Tags': {
            'Project': 'Test',
            'Environment': 'dev',
        },
    }


@pytest.fixture
def sample_stack_config_file(temp_dir, sample_yaml_template, sample_stack_config):
    """Create a sample stack config file with its template."""
    import yaml

    # Write the template
    template_path = os.path.join(temp_dir, 'template.yml')
    with open(template_path, 'w') as f:
        f.write(sample_yaml_template)

    # Write the config
    config_path = os.path.join(temp_dir, 'stack-config.yml')
    with open(config_path, 'w') as f:
        yaml.dump(sample_stack_config, f)

    return config_path


@pytest.fixture
def mock_aws_credentials(monkeypatch):
    """Set up mock AWS credentials for testing."""
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'testing')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'testing')
    monkeypatch.setenv('AWS_SECURITY_TOKEN', 'testing')
    monkeypatch.setenv('AWS_SESSION_TOKEN', 'testing')
    monkeypatch.setenv('AWS_DEFAULT_REGION', 'us-east-1')


@pytest.fixture
def sample_nested_dict():
    """Sample nested dictionary for testing dict operations."""
    return {
        'foo': 123,
        'bar': {
            'color': 'red',
            'weight': 456,
            'nested': {'deep': 'value'},
        },
        'list': [1, 2, 3],
    }


@pytest.fixture
def sample_template_with_includes():
    """Template with IncludedResources section."""
    return """
AWSTemplateFormatVersion: '2010-09-09'
Description: Template with includes
Resources:
  MyBucket:
    Type: AWS::S3::Bucket
IncludedResources:
  MyFunction.*:
    Properties:
      Environment:
        Variables:
          BUCKET: !Ref MyBucket
  ExactMatch: {}
"""


@pytest.fixture
def sample_include_template():
    """Template to be included."""
    return """
AWSTemplateFormatVersion: '2010-09-09'
Description: Included template
Resources:
  MyFunctionHandler:
    Type: AWS::Lambda::Function
    Properties:
      FunctionName: my-handler
      Runtime: python3.9
  MyFunctionProcessor:
    Type: AWS::Lambda::Function
    Properties:
      FunctionName: my-processor
      Runtime: python3.9
  ExactMatch:
    Type: AWS::SNS::Topic
    Properties:
      TopicName: my-topic
  NotIncluded:
    Type: AWS::SQS::Queue
"""
