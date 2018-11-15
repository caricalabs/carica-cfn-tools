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
              help='A template containing resources that be imported in the '
                   '"BaseResource" section')
@click.option('--print-templates/--no-print-templates',
              help='Print transformed templates to stdout before merging')
@click.option('--sam-to-cfn/--no-sam-to-cfn', default=True,
              help='Convert the main and base template from SAM to CloudFormation '
                   'before applying base transforms (this is usually desired)')
@click.option('--extra', '-e', multiple=True,
              help='Include this file or directory as a stack config "Extra"')
@click.argument('stack_config_file')
@click.pass_context
def cli(ctx,
        stack_config_file,
        base_template=None,
        print_templates=False,
        sam_to_cfn=True,
        extra=None):
    ctx.ensure_object(dict)
    ctx.obj['stack'] = Stack(stack_config_file,
                             base_template=base_template,
                             print_templates=print_templates,
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
