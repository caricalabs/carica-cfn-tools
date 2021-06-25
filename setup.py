#!/usr/bin/env python3
"""A setuptools based setup module.
See:
https://packaging.python.org/en/latest/distributing.html
https://github.com/pypa/sampleproject
"""

# Always prefer setuptools over distutils
from codecs import open
from os import path

from setuptools import setup, find_packages

import carica_cfn_tools.version

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='carica_cfn_tools',
    version=carica_cfn_tools.version.__version__,
    description='Tools to manage CloudFormation stack configuration',
    long_description=long_description,
    url='https://github.com/caricalabs/carica-cfn-tools',
    author='Carica Labs, LLC',
    author_email='info@caricalabs.com',
    license='APL 2.0',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 3',
    ],
    keywords='cloudformation cfn stack template config configuration',
    packages=find_packages(exclude=['contrib', 'docs', 'tests']),
    install_requires=[
        'boto3>=1.9.99',
        'click~=6.7',
        'cfn_flip~=1.1.0',
        'aws-sam-translator~=1.9.0',
        'jinja2~=2.10',
    ],
    extras_require={
        'dev': ['check-manifest'],
        'test': [],
    },
    package_data={
    },
    entry_points={
        'console_scripts': [
            'carica-cfn=carica_cfn_tools.cli:cli',
        ],
    },
)
