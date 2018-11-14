#!/usr/bin/env python3
#
# Creates a new CloudFormation stack using a change set, then opens a web browser
# so it can be manually reviewed and executed.

import click

from carica_cfn_tools.stack_config import StackConfig


@click.command()
@click.option('--templates-dir', '-t', default=StackConfig.default_template_dir())
@click.argument('stack_config_file')
def run(stack_config_file, templates_dir=None):
    config = StackConfig(stack_config_file, templates_dir=templates_dir)
    config.create_change_set(change_set_type='CREATE')


if __name__ == '__main__':
    run()
