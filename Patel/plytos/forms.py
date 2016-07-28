"""
forms.py: Creates all the forms used in the pages using
the standard WTForms interface. Does verification regarding
lengths/types for interfacing with users.

__author__ = "Yash Patel"
__copyright__ = "Copyright 2016, Plytos Inc."

__license__ = "Free/Open"
__version__ = "1.0.0"
__maintainer__ = "Yash Patel"
__email__ = "ypatel@princeton.edu"
"""

# from flask.ext.mongoengine.wtf import model_form
from flask_wtf import Form
from wtforms import (TextField, BooleanField, PasswordField, 
    DateTimeField, FloatField, FormField, FieldList, validators)
from flask.ext.mongoengine.wtf.orm import validators

# Login form will provide a Password field (WTForm form field)
class LoginForm(Form):
    username = TextField('Username', validators=[validators.Required()])
    password = PasswordField('Password', validators=[validators.Required()])

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

class SocialMediaForm(Form):
    network       = TextField("Network")
    uname         = TextField("Username")
    url           = TextField("URL")

class VolunteerForm(Form):
    org           = TextField("Organization")
    title         = TextField("Title")
    startDt       = TextField("Start Date")
    endDt         = TextField("End Date")
    url           = TextField("URL")
    impact        = TextField("Impact")

    highlights    = TextField("Highlights")

class WorkForm(Form):
    company       = TextField("Company")
    startDt       = DateTimeField("Start Date", format='%m/%d/%Y', 
        validators=(validators.Optional(),))
    endDt         = DateTimeField("End Date", format='%m/%d/%Y', 
        validators=(validators.Optional(),))
    position      = TextField("Position")
    url           = TextField("URL")
    impact        = TextField("Impact")

    highlights    = TextField("Highlights")
    skills        = TextField("Skills")

class EducationForm(Form):
    school       = TextField("School")
    degree       = TextField("Degree")
    major        = TextField("Major")
    startDt      = DateTimeField("Start Date", format='%m/%d/%Y', 
        validators=(validators.Optional(),))
    gradDt       = DateTimeField("End Date", format='%m/%d/%Y', 
        validators=(validators.Optional(),))
    gpa          = FloatField("GPA")

    courses      = TextField("Courses")

class AwardForm(Form):
    title        = TextField("Title")
    date         = DateTimeField("Date", format='%m/%d/%Y', 
        validators=(validators.Optional(),))
    issuer       = TextField("Issuer")
    desc         = TextField("Description")
    url          = TextField("URL")

class ResumeForm(Form):
    skills       = TextField('Skills')
    pubs         = TextField('Publications')
    interests    = TextField('Interests')
    languages    = TextField('Languages')

class CommentForm(Form):
    topic        = TextField('Topic')
    section      = TextField('Section')
    payload      = TextField('Payload')