"""
decorators.py: Miscellaneous decorator functions used for
establishing some of the routes and misc functionality 
(i.e. forget password emailing).

__author__ = "Yash Patel"
__copyright__ = "Copyright 2016, Plytos Inc."

__license__ = "Free/Open"
__version__ = "1.0.0"
__maintainer__ = "Yash Patel"
__email__ = "ypatel@princeton.edu"
"""

from flask import g
from functools import wraps
from threading import Thread

def async(f):
    """ Allows function to be run asynchrously to Flask app 
    
    Keyword arguments:
    f -- Function to be run
    """
    def wrapper(*args, **kwargs):
        thread = Thread(target=f, args=args, kwargs=kwargs)
        thread.start()
    return wrapper

def login_required(f):
    """ Forces function passed in to be run only if a user
    is currently logged in

    Keyword arguments:
    f -- Function to be run
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            return "Not logged in"
        return f(*args, **kwargs)
    return decorated_function