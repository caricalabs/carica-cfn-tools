carica-cfn-tools - Tools to manage CloudFormation stack configuration
==================================================================================

Simple command line tools to create and update CloudFormation stacks that
make it easy to version-control both your templates and stack configurations
in one place.  Supports a few proprietary transforms useful for dynamically
merging a manually maintained template with a generated template (for example,
sam.json from "chalice package") that contains resources you'd like to include
in your main template.

Development
-----------

The ``vinstall`` script uses virtualenv to prepare a Python environment useful
for development, so you don't have to build and install carica-cfn-tools to be
able to run and test it.

#. Run ``./vinstall``
#. Activate the virtualenv by running ``. ./venv/bin/activate``
#. The ``console_scripts`` listed in ``setup.py`` are now in your path, so you
   can simply run them like:

   ``carica-cfn ...``

Sample Stack Config
-------------------
::

    Region: us-east-1
    Bucket: mycorp-cfn-us-east-1
    Name: WarehouseApp
    Template: ../templates/warehouse-app.yml
    Parameters:
      # Normal parameter values can include strings, numbers, booleans, etc.
      Stage: dev
      TableReadCapacityUnits: 10
      TableWriteCapacityUnits: 5
      AdminPassword:
        # A parameter with a "ParameterStore" sub-key will be resolved to the
        # SSM Parameter Store parameter with that name.
        ParameterStore: dev.warehouseapp.admin-password
      PostgreSQLPassword:
        # A parameter with a "SecretsManager" sub-key will be resolved to the
        # Secrets Manager secret with that ID.
        SecretsManager: dev.warehouseapp.postgresql-password
