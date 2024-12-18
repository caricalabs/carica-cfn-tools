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

The ``vinstall`` script uses the `venv` module to prepare a Python environment useful
for development, so you don't have to build and install carica-cfn-tools to be
able to run and test it.

#. Run ``./vinstall``
#. Activate the virtual environment by running ``. ./venv/bin/activate``
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
    Jinja: true
    Tags:
      env: dev
      scale: large
      cost: small
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
    Extras:
      - ../cfn/static/logo.png
      - ../cfn/static/index.html
    JinjaExtras:
      - ../cfn/includes/*.yml
    JinjaExtrasContext:
      FOO: bar


`Region` sets where the CloudFormation template and related resources will be
uploaded and where the CloudFormation stack will be created.  This must match
the region the `Bucket` was created in.  This is required.

`Bucket` sets where the CloudFormation template and related resources will be
uploaded.  This is required.

`Name` sets the name of the CloudFormation stack.  This is required.

`Template` is a relative path to the CloudFormation YAML or JSON template
file to create the stack from.  This is required.

`Jinja` is an optional setting that controls whether `Template` will be
processed with Jinja2 before being uploaded.  This setting does not enable
Jinja2 for extras; use `JinjaExtras` for that.

`Tags` may be used to set tags on the CloudFormation stack.  CloudFormation
propogates stack tags to the resources inside the stack, so this can be
a convenient way to set tags on resources in your template.

`Extras` and `JinjaExtras` can be absolute paths or glob patterns relative to
the stack config file.

`Extras` or `JinjaExtras` that are directories, whether specified by absolute
path or expanded from a glob pattern, are copied recursively into the deployment
at a top-level directory named after the *last* directory component of the source.
An extra directory path like `/foo/bar/baz` ends up as `/baz` in the deployment.

`Extras` or `JinjaExtras` that are files, whether by absolute path or expanded
from a glob pattern, are copied into the root of the deployment.

`JinjaExtras` are processed with the Jinja2 template engine after all extras
are copied to a temporary directory.

`JinjaExtrasContext` is a dictionary passed as the context when Jinja is run.
