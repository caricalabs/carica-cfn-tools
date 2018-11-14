"""
Creates a new CloudFormation stack using a change set, then opens a web browser
so it can be manually reviewed and executed.
"""
import sys

import click

from carica_cfn_tools.stack_config import StackConfig, CaricaCfnToolsError


@click.command()
@click.option('--base-template', '-b', help='A template from which resources can be included '
                                            'with "Type: Carica::BaseResource"')
@click.option('--extra', '-e', help='Include this file or directory as a stack config "Extra"',
              multiple=True)
@click.argument('stack_config_file')
def main(stack_config_file, base_template=None, extra=None):
    try:
        config = StackConfig(stack_config_file, base_template=base_template, extras=extra)
        config.create_change_set(change_set_type='CREATE')
    except CaricaCfnToolsError as e:
        print('ERROR: ' + str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
