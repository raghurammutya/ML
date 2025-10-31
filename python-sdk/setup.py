"""
Setup script for stocksblitz SDK.
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="stocksblitz",
    version="0.2.0",
    author="StocksBlitz",
    author_email="support@stocksblitz.com",
    description="Intuitive Python SDK for algorithmic trading with advanced services (Alerts, Messaging, Calendar, News)",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/raghurammutya/ML",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: Financial and Insurance Industry",
        "Topic :: Office/Business :: Financial :: Investment",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.8",
    install_requires=[
        "httpx>=0.25.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
        ],
    },
    keywords="trading, algorithmic-trading, stocks, options, technical-indicators",
    project_urls={
        "Bug Reports": "https://github.com/raghurammutya/ML/issues",
        "Source": "https://github.com/raghurammutya/ML",
        "Documentation": "https://github.com/raghurammutya/ML/blob/main/python-sdk/README.md",
    },
)
