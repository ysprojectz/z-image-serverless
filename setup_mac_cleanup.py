"""
Setup script for Mac Cleanup App.
"""

from setuptools import setup, find_packages

setup(
    name="mac-cleanup",
    version="1.0.0",
    description="A Mac cleanup utility to remove junk files and free up disk space",
    author="Mac Cleanup Team",
    author_email="",
    url="https://github.com/yourusername/mac-cleanup",
    packages=find_packages(),
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "mac-cleanup=mac_cleanup.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: MacOS :: MacOS X",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: System :: Systems Administration",
        "Topic :: Utilities",
    ],
    keywords="mac cleanup junk files cache cleaner macos utility",
)
