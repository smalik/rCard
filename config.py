"""
config.py: Module-level file used for providing values of
constants with respect to the execution of the Flask app

__author__ = "Yash Patel"
__copyright__ = "Copyright 2016, Plytos Inc."

__license__ = "Free/Open"
__version__ = "1.0.0"
__maintainer__ = "Yash Patel"
__email__ = "ypatel@princeton.edu"
"""

# Determines which DB to which connection occurs
MONGODB_SETTINGS = {'DB': 'plytos'}

# Creates log/debug mode for executing Flask in browser
DEBUG = True

# Secret key used for WTForms -- prevents XSS
SECRET_KEY = "s3cretk3yish3r3"