from flask import Flask, render_template
from flask.ext.mail import Mail
from flask.ext.login import LoginManager
from flask.ext.bcrypt import Bcrypt
from flask_mongoengine import MongoEngine
from flask.ext.pymongo import PyMongo

app = Flask(__name__)
app.config['MONGODB_SETTINGS'] = {'DB': 'plytos'}
app.debug = True
app.secret_key = "s3cretk3yish3r3"

db = MongoEngine()
db.init_app(app)

mail = Mail(app)

login_manager = LoginManager()
login_manager.init_app(app)

flask_bcrypt = Bcrypt(app)