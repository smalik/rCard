from flask import g
from functools import wraps
from threading import Thread

#TODO timed, jsonp http://flask.pocoo.org/snippets/category/decorators/

def async(f):
    def wrapper(*args, **kwargs):
        thread = Thread(target=f, args=args, kwargs=kwargs)
        thread.start()
    return wrapper

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            return "Not logged in"
        return f(*args, **kwargs)
    return decorated_function