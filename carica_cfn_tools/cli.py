import sys

import click

import carica_cfn_tools.version
from carica_cfn_tools.stack_config import Stack, CaricaCfnToolsError, Action


class ActionParamType(click.Choice):
    def __init__(self):
        super().__init__([str(action.value) for action in Action])

    def convert(self, value, param, ctx):
        if isinstance(value, Action):
            return value
        return Action(super().convert(value, param, ctx))


ACTION_HELP = f'CloudFormation action to perform (default is {Action.CREATE_OR_UPDATE.value})'
DIRECT_HELP = 'Make changes to the stack directly instead of through a change set'
INC_TEMPLATE_HELP = 'Make resources in this SAM or CloudFormation template available for ' \
                    'inclusion in the stack\'s main template\'s "IncludedResources" section ' \
                    '(you can use this option multiple times)'
SAM_TO_CFN_HELP = 'Convert the stack\'s main template and all included templates from SAM to ' \
                  'CloudFormation before performing inclusions'
EXTRA_HELP = 'Include files and directories matched by this glob pattern as stack config "Extras" ' \
             'that gets uploaded to S3 with other dependent resources (you can use this option ' \
             'multiple times)'
JEXTRA_HELP = 'Include files and directories match by this glob pattern like normal "Extras" but ' \
              'process matched files with the Jinja2 template engine before uploading'
VERBOSE_HELP = 'Print extra information while processing templates'


@click.command()
@click.argument('stack_config')
@click.option('--action', '-a', type=ActionParamType(), default=Action.CREATE_OR_UPDATE, help=ACTION_HELP)
@click.option('--direct', '-d', is_flag=True, help=DIRECT_HELP)
@click.option('--include-template', '-i', multiple=True, help=INC_TEMPLATE_HELP)
@click.option('--sam-to-cfn/--no-sam-to-cfn', default=True, help=SAM_TO_CFN_HELP)
@click.option('--extra', '-e', multiple=True, help=EXTRA_HELP)
@click.option('--jextra', '-j', multiple=True, help=JEXTRA_HELP)
@click.option('--verbose/--no-verbose', '-v', help=VERBOSE_HELP)
@click.version_option(version=carica_cfn_tools.version.__version__)
def cli(stack_config, action, direct, include_template, sam_to_cfn, verbose, extra, jextra):
    """
    Create or update the CloudFormation stack specified in STACK_CONFIG.
    """
    try:
        stack = Stack(stack_config, include_template, sam_to_cfn, extra, jextra, verbose)
        if direct:
            stack.apply_stack(action)
        else:
            stack.apply_change_set(action)
    except CaricaCfnToolsError as e:
        print('ERROR: ' + str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    cli()
