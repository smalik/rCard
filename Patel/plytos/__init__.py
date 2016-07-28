"""
__init__.py: Module-level executable called by run.py. Sets up
the basic functionality of the Flask application and its
constituent parts (i.e. interaction w/ mail, login, DB)

__author__ = "Yash Patel"
__copyright__ = "Copyright 2016, Plytos Inc."

__license__ = "Free/Open"
__version__ = "1.0.0"
__maintainer__ = "Yash Patel"
__email__ = "ypatel@princeton.edu"
"""

from flask import Flask
from flask.ext.mail import Mail
from flask.ext.login import LoginManager
from flask.ext.bcrypt import Bcrypt
from flask_mongoengine import MongoEngine

app = Flask(__name__)
app.config.from_object('config')

db = MongoEngine()
db.init_app(app)

mail = Mail(app)

login_manager = LoginManager()
login_manager.init_app(app)

flask_bcrypt = Bcrypt(app)

from plytos.views.jobs import jobs_app
from plytos.views.resume import resume_app
from plytos.views.auth import auth_login
from plytos.views.analytics import analytics_app

app.register_blueprint(auth_login, url_prefix='/user')
app.register_blueprint(jobs_app, url_prefix='/jobs')
app.register_blueprint(resume_app, url_prefix='/resumes')
app.register_blueprint(analytics_app, url_prefix='/analytics')