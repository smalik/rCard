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

####################### Authentication Forms #################################

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
    website           = TextField("URL")

############################ Profile Forms #################################

class BasicForm(Form):
    """ Adds a new personal (basics) entry to user """
    firstName   = TextField('First Name', validators=(validators.Optional(),))
    lastName    = TextField('Last Name', validators=(validators.Optional(),))
    middleName  = TextField('Middle Name', validators=(validators.Optional(),))
    headline    = TextField('Headline', validators=(validators.Optional(),))
    picture     = TextField('Picture', validators=(validators.Optional(),))
    phone       = TextField('Phone', validators=(validators.Optional(),))
    url         = TextField('URL', validators=(validators.Optional(),))

class LocationForm(Form):
    address1    = TextField('Address 1', validators=(validators.Optional(),))
    address2    = TextField('Address 2', validators=(validators.Optional(),))
    zipcode     = TextField('Zipcode')
    city        = TextField('City', validators=(validators.Optional(),))
    country     = TextField('Country', validators=(validators.Optional(),))
    region      = TextField('Region', validators=(validators.Optional(),))

class SocialProfileForm(Form):
    network     = TextField('Network')
    uname       = TextField('Username', validators=(validators.Optional(),))
    url         = TextField('URL', validators=(validators.Optional(),))

############################ Editing Forms #################################

class VolunteerForm(Form):
    """ Adds a new volunteer entry to user resume """
    organization  = TextField("Organization")

    position         = TextField("Title", validators=(validators.Optional(),))
    startDate    = DateTimeField("Start Date", format='%m/%d/%Y', 
        validators=(validators.Optional(),))
    endDate      = DateTimeField("End Date", format='%m/%d/%Y', 
        validators=(validators.Optional(),))
    website           = TextField("URL", validators=(validators.Optional(),))
    highlights        = TextField("Highlights", validators=(validators.Optional(),))

class WorkForm(Form):
    """ Adds a new work entry to user resume """
    company       = TextField("Company")

    startDate       = DateTimeField("Start Date", format='%m/%d/%Y', 
        validators=(validators.Optional(),))
    endDate         = DateTimeField("End Date", format='%m/%d/%Y', 
        validators=(validators.Optional(),))
    position      = TextField("Position", validators=(validators.Optional(),))
    website       = TextField("URL", validators=(validators.Optional(),))
    highlights    = TextField("Highlights", validators=(validators.Optional(),))

class EducationForm(Form):
    """ Adds a new education entry to user resume """
    institution       = TextField("School")
    
    studyType       = TextField("Degree", validators=(validators.Optional(),))
    area            = TextField("Major", validators=(validators.Optional(),))
    start_date      = DateTimeField("Start Date", format='%m/%d/%Y',
        validators=(validators.Optional(),))
    grad_date       = DateTimeField("End Date", format='%m/%d/%Y',
        validators=(validators.Optional(),))
    gpa             = FloatField("GPA", validators=(validators.Optional(),))
    courses         = TextField("Courses", validators=(validators.Optional(),))

class AwardForm(Form):
    """ Adds a new awards entry to user resume """
    title        = TextField("Title")
    
    date         = DateTimeField("Date", format='%m/%d/%Y', 
        validators=(validators.Optional(),))
    awarder       = TextField("Issuer", validators=(validators.Optional(),))
    summary       = TextField("Description", validators=(validators.Optional(),))
    
class SkillForm(Form):
    """ Adds a new skills entry to user resume """
    name         = TextField("Name")
    level        = TextField("Level", validators=(validators.Optional(),))

class PublicationForm(Form):
    """ Adds a new publication entry to user resume """
    name            = TextField("Name")
    publisher       = TextField("Publisher", validators=(validators.Optional(),))
    releaseDate    = DateTimeField("Publication Date", format='%m/%d/%Y', 
        validators=(validators.Optional(),))
    website         = TextField("Website", validators=(validators.Optional(),))
    summary         = TextField("Summary", validators=(validators.Optional(),))

class InterestForm(Form):
    """ Adds a new interest entry to user resume """
    name         = TextField("Name")

class LanguageForm(Form):
    """ Adds a new language entry to user resume """
    language     = TextField("Language")
    fluency      = TextField("Fluency", validators=(validators.Optional(),))

class ResumeForm(Form):
    """ Adds a new resume entry to user """
    skills       = TextField('Skills')
    pubs         = TextField('Publications')
    interests    = TextField('Interests')
    languages    = TextField('Languages')

############################ Editing Forms #################################

class CommentForm(Form):
    """ Adds a new comment entry to any relevant object """
    topic        = TextField('Topic')
    section      = TextField('Section')
    payload      = TextField('Payload')

class TodoForm(Form):
    """ Adds a new todo entry to any relevant object """
    payload      = TextField('Payload')