import sys

import click

import carica_cfn_tools.version
from carica_cfn_tools.stack_config import Stack, CaricaCfnToolsError


def _create_change_set(stack_config, include_template, sam_to_cfn, extra, jextra, verbose, change_set_type):
    try:
        stack = Stack(stack_config, include_template, sam_to_cfn, extra, jextra, verbose)
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
EXTRA_HELP = 'Include files and directories matched by this glob pattern as stack config "Extras" ' \
             'that gets uploaded to S3 with other dependent resources (you can use this option ' \
             'multiple times)'
JEXTRA_HELP = 'Include files and directories match by this glob pattern like normal "Extras" but ' \
              'process matched files with the Jinja2 template engine before uploading'


@click.group()
@click.version_option(version=carica_cfn_tools.version.__version__)
def cli():
    pass


@cli.command()
@click.argument('stack_config')
@click.option('--include-template', '-i', multiple=True, help=INC_TEMPLATE_HELP)
@click.option('--sam-to-cfn/--no-sam-to-cfn', default=True, help=SAM_TO_CFN_HELP)
@click.option('--extra', '-e', multiple=True, help=EXTRA_HELP)
@click.option('--jextra', '-j', multiple=True, help=JEXTRA_HELP)
@click.option('--verbose/--no-verbose', '-v', help=PRINT_HELP)
def create(stack_config, include_template, sam_to_cfn, verbose, extra, jextra):
    _create_change_set(stack_config, include_template, sam_to_cfn, extra, jextra, verbose, 'CREATE')


@cli.command()
@click.argument('stack_config')
@click.option('--include-template', '-i', multiple=True, help=INC_TEMPLATE_HELP)
@click.option('--sam-to-cfn/--no-sam-to-cfn', default=True, help=SAM_TO_CFN_HELP)
@click.option('--extra', '-e', multiple=True, help=EXTRA_HELP)
@click.option('--jextra', '-j', multiple=True, help=JEXTRA_HELP)
@click.option('--verbose/--no-verbose', '-v', help=PRINT_HELP)
def update(stack_config, include_template, sam_to_cfn, verbose, extra, jextra):
    _create_change_set(stack_config, include_template, sam_to_cfn, extra, jextra, verbose, 'UPDATE')


if __name__ == '__main__':
    cli()
