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

from flask import Flask, session
from flask.ext.mail import Mail
from flask.ext.login import LoginManager
from flask.ext.bcrypt import Bcrypt
from flask_mongoengine import MongoEngine

# Application object configured to the settings set up
# in the config.py file
app = Flask(__name__)
app.config.from_object('config')

########################### MongoDB Setup ###############################
# MongoDB back-end	 database
db = MongoEngine()
db.init_app(app)

# Registers each of the DBs the application will save to
db.register_connection("users", name="users")
db.register_connection("resumes", name="resumes")
db.register_connection("todos", name="todos")

# Each comments section has own DB associated to it
db.register_connection("work_comments", name="work_comments")
db.register_connection("volunteer_comments", name="volunteer_comments")
db.register_connection("education_comments", name="education_comments")
db.register_connection("awards_comments", name="awards_comments")

db.register_connection("skills_comments", name="skills_comments")
db.register_connection("publications_comments", name="publications_comments")
db.register_connection("interests_comments", name="interests_comments")
db.register_connection("languages_comments", name="languages_comments")

mail = Mail(app)

login_manager = LoginManager()
login_manager.init_app(app)

flask_bcrypt = Bcrypt(app)

# Sets up the routes for each of the sub-app classes
from plytos.views.jobs import jobs_app
from plytos.views.resume import resume_app
from plytos.views.auth import auth_app
from plytos.views.analytics import analytics_app
from plytos.views.money import money_app
from plytos.views.network import network_app

app.register_blueprint(auth_app, url_prefix='/user')
app.register_blueprint(jobs_app, url_prefix='/jobs')
app.register_blueprint(resume_app, url_prefix='/resumes')
app.register_blueprint(analytics_app, url_prefix='/analytics')
app.register_blueprint(money_app, url_prefix='/purchase')
app.register_blueprint(network_app, url_prefix='/network')