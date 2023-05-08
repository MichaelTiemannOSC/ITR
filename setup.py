from setuptools import setup, find_packages

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name='ITR',
    version='2.0.0b1',
    description='Assess the temperature alignment of current targets, commitments, and investment '
                'and lending portfolios.',
    long_description=long_description,
    long_description_content_type="text/markdown",
    author='Ortec Finance',
    author_email='joris.cramwinckel@ortec-finance.com',
    packages=find_packages(),
    download_url="https://pypi.org/project/ITR-Temperature-Alignment-Tool/",
    url="https://github.com/os-climate/ITR",
    project_urls={
        "Bug Tracker": "https://github.com/os-climate/ITR",
        "Documentation": 'https://github.com/os-climate/ITR',
        "Source Code": "https://github.com/os-climate/ITR",
    },
    keywords=['Climate', 'ITR', 'Finance'],
    package_data={
        'ITR': ['data/input/*.csv'],
    },
    include_package_data=True,
    install_requires=[
                      'dash>=2.9.3',
                      'dash_bootstrap_components>=1.4.1',
                      'diskcache>=5.6.1',
                      'iam-units>=2022.10.27',
                      # jupyter==1.0.0
                      'matplotlib>=3.7.1',
                      'multiprocess==0.70.14',
                      'openpyxl>=3.0.10',
                      'openscm-units>=0.5.1',
                      'osc-ingest-tools==0.4.3',
                      'pandas>=1.5.3',
                      'pint==0.20.1',
                      'pint-pandas==0.3',
                      'pip>=22.0.3',
                      'pydantic>=1.10.2',
                      'pygithub==1.55',
                      'pytest==7.3.1',
                      'python-dotenv==1.0.0',
                      'setuptools>=65.5.1',
                      'Sphinx==5.1.1',
                      'sphinx-autoapi==1.9.0',
                      'sphinx-autodoc-typehints==1.19.1',
                      'sphinx-rtd-theme==1.0.0',
                      'SQLAlchemy==1.4.48',
                      'trino==0.323.0',
                      'wheel>=0.36.2',
                      'xlrd>=2.0.1',
                      ],
    python_requires='>=3.8',
    extras_require={
        'dev': [
            'nose2',
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: Unix",
        "Operating System :: MacOS",
        "Intended Audience :: Science/Research",
        "Intended Audience :: Developers",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3 :: Only",
        "Topic :: Software Development",
        "Topic :: Office/Business :: Financial",
        "Topic :: Scientific/Engineering"

    ],
    test_suite='nose2.collector.collector',
)
