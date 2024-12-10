import sys
from typing import Iterable

import click
from click import BadParameter

import carica_cfn_tools.version
from carica_cfn_tools.stack_config import Stack, CaricaCfnToolsError, Action
from carica_cfn_tools.utils import dict_find_path


class ActionParamType(click.Choice):
    def __init__(self):
        super().__init__([str(action.value) for action in Action])

    def convert(self, value, param, ctx):
        if isinstance(value, Action):
            return value
        return Action(super().convert(value, param, ctx))


ACTION_HELP = f'CloudFormation action to perform (default is {Action.CREATE_OR_UPDATE.value})'
BROWSER_HELP = 'Open a web browser to view the changeset or stack'
DIRECT_HELP = 'Make changes to the stack directly instead of through a change set'
IGNORE_EMPTY_UPDATES_HELP = 'Ignore "No updates are to be performed." errors when updating stacks'
WAIT_HELP = 'Wait for creates and updates to finish before exiting'
WAIT_TIMEOUT_HELP = 'Wait this many seconds when --wait is used (default 3600)'
ROLE_ARN_HELP = 'Use this value as the RoleARN argument creating or updating stacks and changesets'
INC_TEMPLATE_HELP = 'Make resources in this SAM or CloudFormation template available for ' \
                    'inclusion in the stack\'s main template\'s "IncludedResources" section ' \
                    '(you can use this option multiple times)'
SAM_TO_CFN_HELP = 'Convert the stack\'s main template and all included templates from SAM to ' \
                  'CloudFormation before performing inclusions'
EXTRA_HELP = 'Include files and directories matched by this glob pattern as stack config "Extras" ' \
             'that gets uploaded to S3 with other dependent resources (you can use this option ' \
             'multiple times)'
PACKAGE_EXTRA_HELP = 'Include files and directories matched by this glob pattern as stack config "PackageExtras" ' \
                     'that get copied into the local temp dir before running `aws cloudformation package`' \
                     '(you can use this option multiple times)'
JINJA_HELP = 'Process the SAM or CloudFormation template with the Jinja2 template engine after ' \
             'included templates are processed (deprecated; use "Jinja" config key instead) '
JEXTRA_HELP = 'Include files and directories match by this glob pattern like normal "Extras" but ' \
              'process matched files with the Jinja2 template engine before uploading'
QUERY_HELP = 'Print the value of the specified stack config key to stdout; use dot path notation ' \
             'like "Parameters.SomeParameter"; (does not create or modify any stacks)'
TAG_HELP = 'Set this tag on the CloudFormation stack (format like "key=value"); may be ' \
           'specified multiple times; these values override values set in the Tag section in ' \
           'the stack config file'
VERBOSE_HELP = 'Print extra information while processing templates'


def parse_tags(tags: Iterable[str]) -> dict[str, str]:
    tags_dict = {}
    for tag in tags:
        k, sep, val = tag.partition('=')
        if not k or not sep or not val:
            raise BadParameter(f'Tag option value "{tag}" must be formatted like "key=value"')
        tags_dict[k] = val
    return tags_dict


@click.command()
@click.argument('stack_config')
@click.option('--action', '-a', type=ActionParamType(), default=Action.CREATE_OR_UPDATE, help=ACTION_HELP)
@click.option('--browser', '-b', is_flag=True, help=BROWSER_HELP)
@click.option('--direct', '-d', is_flag=True, help=DIRECT_HELP)
@click.option('--ignore-empty-updates', '-g', is_flag=True, help=IGNORE_EMPTY_UPDATES_HELP)
@click.option('--wait', '-w', is_flag=True, help=WAIT_HELP)
@click.option('--wait-timeout', '-W', help=WAIT_TIMEOUT_HELP)
@click.option('--role-arn', '-r', help=ROLE_ARN_HELP)
@click.option('--include-template', '-i', multiple=True, help=INC_TEMPLATE_HELP)
@click.option('--sam-to-cfn/--no-sam-to-cfn', default=True, help=SAM_TO_CFN_HELP)
@click.option('--extra', '-e', multiple=True, help=EXTRA_HELP)
@click.option('--package-extra', multiple=True, help=PACKAGE_EXTRA_HELP)
@click.option('--jinja/--no-jinja', '-J', default=False, help=JINJA_HELP)
@click.option('--jextra', '-j', multiple=True, help=JEXTRA_HELP)
@click.option('--query', '-q', help=QUERY_HELP)
@click.option('--tag', '-t', help=TAG_HELP, multiple=True)
@click.option('--verbose/--no-verbose', '-v', help=VERBOSE_HELP)
@click.version_option(version=carica_cfn_tools.version.__version__)
def cli(stack_config, action, browser, direct, ignore_empty_updates, wait, role_arn, include_template, sam_to_cfn,
        verbose, extra, jinja, jextra, package_extra, query, tag, wait_timeout):
    """
    Create or update the CloudFormation stack specified in STACK_CONFIG.
    """
    # Parse arguments.
    tags = parse_tags(tag)
    if wait_timeout:
        wait_timeout = int(wait_timeout)
    else:
        wait_timeout = 3600

    try:
        stack = Stack(stack_config, include_template, sam_to_cfn, extra, jinja, jextra, package_extra, verbose, tags)
        if query:
            val = dict_find_path(stack.raw_config, query)
            if not val:
                print(f'ERROR: Key "{query}" not found in stack config')
                sys.exit(1)
            print(val)
        elif direct:
            stack.apply_stack(action, browser, wait, wait_timeout, ignore_empty_updates, role_arn)
        else:
            stack.apply_change_set(action, browser, wait, wait_timeout, ignore_empty_updates, role_arn)
    except CaricaCfnToolsError as e:
        print('ERROR: ' + str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    cli()
