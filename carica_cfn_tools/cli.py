import sys

import click

from carica_cfn_tools.stack_config import Stack, CaricaCfnToolsError


def _create_change_set(stack, change_set_type):
    try:
        stack.create_change_set(change_set_type=change_set_type)
    except CaricaCfnToolsError as e:
        print('ERROR: ' + str(e), file=sys.stderr)
    sys.exit(1)


@click.group()
@click.option('--base-template', '-b',
              help='A template from which resources can be included with '
                   '"Type: Carica::BaseResource"')
@click.option('--print-template/--no-print-template',
              help='Print the template to stdout uploading it to S3')
@click.option('--sam-to-cfn/--no-sam-to-cfn',
              help='Convert the main and base template from SAM to CloudFormation '
                   'before applying base transforms')
@click.option('--extra', '-e', multiple=True,
              help='Include this file or directory as a stack config "Extra"')
@click.argument('stack_config_file')
@click.pass_context
def cli(ctx,
        stack_config_file,
        base_template=None,
        print_template=False,
        sam_to_cfn=False,
        extra=None):
    ctx.ensure_object(dict)
    ctx.obj['stack'] = Stack(stack_config_file,
                             base_template=base_template,
                             print_template=print_template,
                             convert_sam_to_cfn=sam_to_cfn,
                             extras=extra)


@cli.command()
@click.pass_context
def create(ctx):
    _create_change_set(ctx.obj['stack'], 'CREATE')


@cli.command()
@click.pass_context
def update(ctx):
    _create_change_set(ctx.obj['stack'], 'UPDATE')


if __name__ == '__main__':
    cli()
