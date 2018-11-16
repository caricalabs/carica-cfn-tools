import sys

import click

from carica_cfn_tools.stack_config import Stack, CaricaCfnToolsError


def _create_change_set(stack_config, include_template, sam_to_cfn, extra, verbose, change_set_type):
    try:
        stack = Stack(stack_config, include_template, sam_to_cfn, extra, verbose)
        stack.create_change_set(change_set_type=change_set_type)
    except CaricaCfnToolsError as e:
        print('ERROR: ' + str(e), file=sys.stderr)
    sys.exit(1)


PRINT_HELP = 'Print extra information while processing templates'
INC_TEMPLATE_HELP = 'Make resources in this SAM or CloudFormation template available for ' \
                    'inclusion in the stack\'s main template\'s "IncludedResources" section ' \
                    '(you can use this option multiple times)'
SAM_TO_CFN_HELP = 'Convert the stack\'s main template and all included templates from SAM to ' \
                  'CloudFormation before performing inclusions'
EXTRA_HELP = 'Include this file or directory as a stack config "Extra" that gets uploaded to ' \
             'S3 with other dependent resources (you can use this option multiple times)'


@click.group()
def cli():
    pass


@cli.command()
@click.argument('stack_config')
@click.option('--include-template', '-i', multiple=True, help=INC_TEMPLATE_HELP)
@click.option('--sam-to-cfn/--no-sam-to-cfn', default=True, help=SAM_TO_CFN_HELP)
@click.option('--extra', '-e', multiple=True, help=EXTRA_HELP)
@click.option('--verbose/--no-verbose', '-v', help=PRINT_HELP)
def create(stack_config, include_template, sam_to_cfn, verbose, extra):
    _create_change_set(stack_config, include_template, sam_to_cfn, extra, verbose, 'CREATE')


@cli.command()
@click.argument('stack_config')
@click.option('--include-template', '-i', multiple=True, help=INC_TEMPLATE_HELP)
@click.option('--sam-to-cfn/--no-sam-to-cfn', default=True, help=SAM_TO_CFN_HELP)
@click.option('--extra', '-e', multiple=True, help=EXTRA_HELP)
@click.option('--verbose/--no-verbose', '-v', help=PRINT_HELP)
def update(stack_config, include_template, sam_to_cfn, verbose, extra):
    _create_change_set(stack_config, include_template, sam_to_cfn, extra, verbose, 'UPDATE')


if __name__ == '__main__':
    cli()
