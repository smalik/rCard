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

from flask_wtf import Form
from wtforms import (TextField, BooleanField, PasswordField, 
    DateTimeField, FloatField, FormField, FieldList, validators)
from flask.ext.mongoengine.wtf.orm import validators

class LoginForm(Form):
    """ Login form for authenticating previously-registered user """
    username = TextField('Username', validators=[validators.Required()])
    password = PasswordField('Password', validators=[validators.Required()])

class RegisterForm(Form):
    """ Login form for creating new user in Mongo DB """
    username = TextField(label='Username', validators=[validators.Required(), 
        validators.Length(min=5, max=25)])
    email = TextField('Email', validators=[validators.Required()])
    password = PasswordField('Password', validators=[validators.Required(), 
        validators.Length(min=6, max=40)])
    confirm  = PasswordField('Repeat Password', validators=[validators.Required(), 
        validators.EqualTo('password', message='Passwords must match')])

class ForgotForm(Form):
    """ Creates a request to reset the original password stored
    with the account specified
    """
    username = TextField('Username', validators=[validators.Required()])

class ResetPassForm(Form):
    """ Form where the password is reset (after ForgotForm complete) """
    password = PasswordField('Password', validators=[validators.Required(), 
        validators.Length(min=6, max=40)])
    confirm  = PasswordField('Repeat Password', validators=[validators.Required(), 
        validators.EqualTo('password', message='Passwords must match')])

class SocialMediaForm(Form):
    """ Adds a new social media hook to user profile/account """
    network       = TextField("Network")
    uname         = TextField("Username")
    url           = TextField("URL")

class VolunteerForm(Form):
    """ Adds a new volunteer entry to user resume """
    org           = TextField("Organization")
    title         = TextField("Title")
    startDt       = TextField("Start Date")
    endDt         = TextField("End Date")
    url           = TextField("URL")
    impact        = TextField("Impact")

    highlights    = TextField("Highlights")

class WorkForm(Form):
    """ Adds a new work entry to user resume """
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
    """ Adds a new education entry to user resume """
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
    """ Adds a new awards entry to user resume """
    title        = TextField("Title")
    date         = DateTimeField("Date", format='%m/%d/%Y', 
        validators=(validators.Optional(),))
    issuer       = TextField("Issuer")
    desc         = TextField("Description")
    url          = TextField("URL")

class ResumeForm(Form):
    """ Adds a new resume entry to user """
    skills       = TextField('Skills')
    pubs         = TextField('Publications')
    interests    = TextField('Interests')
    languages    = TextField('Languages')

class CommentForm(Form):
    """ Adds a new comment entry to any relevant object """
    topic        = TextField('Topic')
    section      = TextField('Section')
    payload      = TextField('Payload')