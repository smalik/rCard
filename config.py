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

####################### Login Configuration #########################
GOOGLE_LOGIN_CLIENT_ID = "98849433232-irun3c89tjctk1higgr47nn83h4tbn51.apps.googleusercontent.com"
GOOGLE_LOGIN_CLIENT_SECRET = "gHgZtilK3i2wChSYkKr4ipUE"

OAUTH_CREDENTIALS = {
    'facebook': {
        'id': '1125818364132179',
        'secret': 'e135fef3b3440213df503faa4bd62359'
    },
    'twitter': {
        'id': 'iCcTHaxdjJo4yXIxNtBkkuOxC',
        'secret': 'Vhc6Y4ZoMcsRG9rXHmBpziLvqgg2Z1QkimaT6QHRrvpFtKxkFO'
    },
    'google': {
        'id': GOOGLE_LOGIN_CLIENT_ID,
        'secret': GOOGLE_LOGIN_CLIENT_SECRET
    }
}