# from flask.ext.mongoengine.wtf import model_form
from flask_wtf import Form
from wtforms import TextField, BooleanField, PasswordField, validators
from flask.ext.mongoengine.wtf.orm import validators

import models

# user_form = model_form(models.Person, exclude=['password'])

# Login form will provide a Password field (WTForm form field)
class LoginForm(Form):
    username = TextField('Username', validators=[validators.Required()])
    password = PasswordField('Password', validators=[validators.Required()])
    # remember_me = BooleanField('remember_me', default = False)

# Signup Form created from user_form
class RegisterForm(Form):
    username = TextField(label='Username', validators=[validators.Required(), 
        validators.Length(min=5, max=25)])
    email = TextField('Email', validators=[validators.Required()])
    password = PasswordField('Password', validators=[validators.Required(), 
        validators.Length(min=6, max=40)])
    confirm  = PasswordField('Repeat Password', validators=[validators.Required(), 
        validators.EqualTo('password', message='Passwords must match')])

# For resetting password
class ForgotForm(Form):
    username = TextField('Username', validators=[validators.Required()])

class ResetPassForm(Form):
    password = PasswordField('Password', validators=[validators.Required(), 
        validators.Length(min=6, max=40)])
    confirm  = PasswordField('Repeat Password', validators=[validators.Required(), 
        validators.EqualTo('password', message='Passwords must match')])

class ResumeForm(Form):
    experience = TextField('Experience')
    volunteer = TextField('Volunteer')
    education = TextField('Education')
    skills = TextField('Skills')
    awards = TextField('Awards')
    pubs = TextField('Publications')
    interests = TextField('Interests')
    languages = TextField('Languages')

class CommentForm(Form):
    topic = TextField('Topic')
    section = TextField('Section')
    payload = TextField('Payload')