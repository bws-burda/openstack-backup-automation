"""Setup script for OpenStack Backup Automation."""

from setuptools import setup, find_packages
import os

# Read the README file
def read_readme():
    with open("README.md", "r", encoding="utf-8") as fh:
        return fh.read()

# Read requirements
def read_requirements():
    with open("requirements.txt", "r", encoding="utf-8") as fh:
        return [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="openstack-backup-automation",
    version="1.0.0",
    author="OpenStack Backup Automation Team",
    author_email="admin@example.com",
    description="Automated backup and snapshot system for OpenStack resources",
    long_description=read_readme() if os.path.exists("README.md") else "",
    long_description_content_type="text/markdown",
    url="https://github.com/example/openstack-backup-automation",
    packages=find_packages(where="."),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: System :: Archiving :: Backup",
        "Topic :: System :: Systems Administration",
    ],
    python_requires=">=3.8",
    install_requires=read_requirements() if os.path.exists("requirements.txt") else [],
    entry_points={
        "console_scripts": [
            "openstack-backup-automation=src.cli.main:main"
        ],
    },
    include_package_data=True,
    zip_safe=False,
)