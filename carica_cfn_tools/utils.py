import collections
import subprocess
import sys
import urllib.parse
from collections import OrderedDict

import cfn_flip
from cfn_tools import ODict


def get_s3_https_url(region, bucket, key):
    if region == 'us-east-1':
        host = 's3'
    else:
        host = 's3-' + region
    return f'https://{host}.amazonaws.com/{bucket}/{key}'


def get_cfn_console_url_changeset(region, stack_arn, change_set_arn):
    """
    Get is a URL for the "new" (as of 2018-11) CloudFormation console to view
    the specified change set ARN in the specified stack.
    """
    # Must quote with "safe" set to exclude '/' so slashes in the ARNs get escaped as well.
    quoted_stack_arn = urllib.parse.quote(stack_arn, safe='')
    quoted_change_set_arn = urllib.parse.quote(change_set_arn, safe='')

    return f'https://console.aws.amazon.com/cloudformation/home?region={region}#' \
        f'/stacks/changesets/changes?stackId={quoted_stack_arn}&changeSetId={quoted_change_set_arn}'


def get_cfn_console_url_stack(region, stack_arn):
    """
    Get is a URL for the "new" (as of 2018-11) CloudFormation console to view
    the specified stack.
    """
    # Must quote with "safe" set to exclude '/' so slashes in the ARNs get escaped as well.
    quoted_stack_arn = urllib.parse.quote(stack_arn, safe='')

    return f'https://console.aws.amazon.com/cloudformation/home?region={region}#' \
        f'/stacks/stackinfo?stackId={quoted_stack_arn}'


def open_url_in_browser(url):
    print()
    print(url)
    if sys.platform == 'darwin':
        command = 'open'
    else:
        command = 'xdg-open'

    try:
        subprocess.Popen([command, url]).communicate()
    except Exception as e:
        pass


def update_dict(d, u):
    """
    Updates a dict recursively from another dict.
    """
    if not isinstance(d, collections.Mapping):
        return u

    for k, v in u.items():
        if isinstance(v, collections.Mapping):
            d[k] = update_dict(d.get(k, {}), v)
        else:
            d[k] = v
    return d


def copy_dict(value, impl=dict):
    """
    Perform a deep copy of a dict using the specified impl for each new dict constructed.
    Preserves the order of items as read from the source dict.

    :param value: the dict value to copy
    :param impl: the function to call to create new dicts
    :return: a deep copy of value, using impl for each dict constructed along the way
    """
    if isinstance(value, tuple):
        return (copy_dict(e) for e in value)
    if isinstance(value, list):
        return [copy_dict(e) for e in value]
    if isinstance(value, dict):
        new_value = impl()
        for k, v in value.items():
            new_value[k] = copy_dict(v, impl=impl)
        return new_value
    return value


def load_cfn_template(template_str):
    """
    Loads a template from a string, detecting the format as JSON or YAML automatically.

    Returns a normal OrderedDict.
    """

    # cfn_flip.load() raises a JSONDecodeError even when the content was YAML (but invalid).
    # So do our own loading here.
    try:
        template_data = cfn_flip.load_json(template_str)
        template_type = 'json'
    except ValueError as json_err:
        try:
            template_data = cfn_flip.load_yaml(template_str)
            template_type = 'yaml'
        except Exception as yaml_err:
            raise ValueError(f'Could not read template as JSON or YAML:\n\t{str(json_err)}\n\t{str(yaml_err)}')

    # cfn_flip.load() can return a cfn_tools.odict.ODict, which is almost
    # immutable because of the way it always returns new lists from items(), but
    # doesn't error.  Return a copy that's a regular mutable OrderedDict so we can
    # avoid unpleasant surprises later.
    return copy_dict(template_data, impl=OrderedDict), template_type


def dump_cfn_template_yaml(template_data, clean_up=False, long_form=False):
    """
    Wrapper around cfn_flip.dump_yaml() that converts the given template data
    to the ODict type it expets.
    """
    return cfn_flip.dump_yaml(copy_dict(template_data, impl=ODict),
                              clean_up=clean_up,
                              long_form=long_form)


def dump_cfn_template_json(template_data):
    """
    Wrapper around cfn_flip.dump_json() that converts the given template data
    to the ODict type it expets.
    """
    return cfn_flip.dump_json(copy_dict(template_data, impl=ODict))
