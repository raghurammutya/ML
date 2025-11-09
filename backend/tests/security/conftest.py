"""
Shared fixtures for security tests.
"""
import os

# Unset ENVIRONMENT if it's set to invalid value
if os.getenv('ENVIRONMENT') == 'dev':
    os.environ.pop('ENVIRONMENT', None)
