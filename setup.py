from setuptools import setup, find_packages

setup(
name='ccanalyser',
version='0.0.6',
author='asmith, dsims',
author_email='alastair.smith@ndcls.ox.ac.uk',
packages=find_packages(),
entry_points={'console_scripts': ['ccanalyser = ccanalyser.cli:cli',]
                                  #'ccpipeline = ccanalyser.cli:main']
            },
include_package_data=True,
url='https://github.com/sims-lab/capture-c.git',
license='LICENSE',
description='Performs complete processing of capture-c data',
long_description=open('README.txt').read(),
long_description_content_type="text/markdown",
python_requires='>=3.8',
install_requires=['pandas>=1',
                  'seaborn>=0.9.0',
                  'pybedtools>=0.8.1',
                  'papermill>=2.1.1',
                  'plotly>=4.8.0',
                  'xopen>=0.7.3',
                  'pysam>=0.15.3',
                  'gevent',
                  'paramiko>=2.7.1',
                  'sqlalchemy>=1.3.18',
                  'cgatcore>=0.6.7',
                  'apsw',
                  'ruffus',
                  'drmaa',
                  'joblib',
                  'ipykernel',
                  'click']
)
