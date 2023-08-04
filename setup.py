from setuptools import setup, find_packages

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="ITR",
    version="2.0.0b2",
    description="Assess the temperature alignment of current targets, commitments, and investment "
    "and lending portfolios.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Ortec Finance",
    author_email="joris.cramwinckel@ortec-finance.com",
    packages=find_packages(),
    download_url="https://pypi.org/project/ITR-Temperature-Alignment-Tool/",
    url="https://github.com/os-climate/ITR",
    project_urls={
        "Bug Tracker": "https://github.com/os-climate/ITR",
        "Documentation": "https://github.com/os-climate/ITR",
        "Source Code": "https://github.com/os-climate/ITR",
    },
    keywords=["Climate", "ITR", "Finance"],
    package_data={
        "ITR": ["data/input/*.csv"],
    },
    include_package_data=True,
    install_requires=[
        "dash==2.9.3",
        "dash_bootstrap_components==1.4.1",
        "diskcache==5.6.1",
        "flask==2.2.5",
        "iam-units==2022.10.27",
        "jupyterlab==4.0.3",
        "matplotlib==3.7.2",
        "multiprocess==0.70.14",
        "openpyxl==3.0.10",
        "openscm-units==0.5.2",
        "orca==1.8",
        "osc-ingest-tools==0.4.3",
        "pandas>=2.0.3",
        "Pint>=0.22.0",
        "Pint-Pandas>=0.4",
        "psutil==5.9.3",
        "pydantic==1.10.8",
        "pygithub==1.55",
        "pytest==7.3.2",
        "python-dotenv==1.0.0",
        "Sphinx==5.1.1",
        "sphinx-autoapi==1.9.0",
        "sphinx-autodoc-typehints==1.19.1",
        "sphinx-rtd-theme==1.0.0",
        "SQLAlchemy==1.4.48",
        "trino==0.326.0",
        "wheel==0.40.0",
        "xlrd==2.0.1",
    ],
    python_requires=">=3.9",
    extras_require={
        "dev": [
            "nose2",
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
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3 :: Only",
        "Topic :: Software Development",
        "Topic :: Office/Business :: Financial",
        "Topic :: Scientific/Engineering",
    ],
    test_suite="nose2.collector.collector",
)
