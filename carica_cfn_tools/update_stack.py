"""
Creates a change set that updates an existing CloudFormation, then opens a web browser
so it can be manually reviewed and executed.
"""
import sys

import click

from carica_cfn_tools.stack_config import Stack, CaricaCfnToolsError


@click.command()
@click.option('--base-template', '-b', help='A template from which resources can be included '
                                            'with "Type: Carica::BaseResource"')
@click.option('--sam-to-cfn', help='Convert the main and base template from SAM to CloudFormation '
                                   'before applying base transforms')
@click.option('--extra', '-e', help='Include this file or directory as a stack config "Extra"',
              multiple=True)
@click.argument('stack_config_file')
def main(stack_config_file, base_template=None, sam_to_cfn=False, extra=None):
    try:
        stack = Stack(stack_config_file, base_template=base_template, convert_sam_to_cfn=sam_to_cfn,
                      extras=extra)
        stack.create_change_set(change_set_type='UPDATE')
    except CaricaCfnToolsError as e:
        print('ERROR: ' + str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
