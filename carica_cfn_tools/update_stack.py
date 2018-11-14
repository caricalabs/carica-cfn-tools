"""
Creates a change set that updates an existing CloudFormation, then opens a web browser
so it can be manually reviewed and executed.
"""
import sys

import click

from carica_cfn_tools.stack_config import StackConfig, CaricaCfnToolsError


@click.command()
@click.option('--base-template', '-b', help='A template from which resources can be included '
                                            'with "Type: Carica::BaseResource"')
@click.argument('stack_config_file')
def main(stack_config_file, base_template=None):
    try:
        config = StackConfig(stack_config_file, base_template=base_template)
        config.create_change_set(change_set_type='UPDATE')
    except CaricaCfnToolsError as e:
        print('ERROR: ' + str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
