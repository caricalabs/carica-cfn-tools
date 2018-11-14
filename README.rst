carica-cfn-tools - Command line tools to manage CloudFormation stack configuration
==================================================================================

Simple command line tools to create and update CloudFormation stacks that
make it easy to version-control both your templates and stack configurations
in one place.

Development
-----------

The ``vinstall`` script uses virtualenv to prepare a Python environment useful
for development, so you don't have to build and install carica-cfn-tools to be
able to run and test it.

#. Run ``./vinstall``
#. Activate the virtualenv by running ``. ./venv/bin/activate``
#. Run modules with a main() function like
   ``python -m carica_cfn_tools.create_stack``

Usage
-----

carica-cnf-tools supports the following commands:

#. create-stack: create a stack from a YAML stack config file
#. update-stack: update an existing stack from a YAML stack config file
