"""
resume.py: Sets up all the resume views, namely all those under
the extension of /resumes/. This includes:
    - View page
    - Create page
    - Find page
    - Edit page
    - Finalized page
    - Review page

__author__ = "Yash Patel"
__copyright__ = "Copyright 2016, Plytos Inc."

__license__ = "Free/Open"
__version__ = "1.0.0"
__maintainer__ = "Yash Patel"
__email__ = "ypatel@princeton.edu"
"""

from flask import (Blueprint, render_template, request, redirect, 
    url_for, g, abort, session)
from flask.views import View
from flask.ext.mongoengine.wtf import model_form
from flask.ext.login import current_user
from flask.ext.principal import (identity_loaded, Permission, RoleNeed,
    UserNeed, AnonymousIdentity, Identity)
from bson.objectid import ObjectId

import json
from collections import namedtuple
from functools import partial
import time
from datetime import datetime

from plytos import app
from plytos.models.resume import Resume
from plytos.models.person import Person

from plytos.views.final import setup_final
from plytos.views.review import setup_review
from plytos.views.edit import setup_edit
from plytos.views.self_resume import setup_self
from plytos.views.todos import setup_todos

ResumeNeed = namedtuple('resume', ['method', 'value'])
EditResumeNeed = partial(ResumeNeed, 'edit')

resume_app = Blueprint('resume_app', __name__, template_folder='templates')
setup_final(resume_app)
setup_review(resume_app)
setup_edit(resume_app)
setup_self(resume_app)
setup_todos(resume_app)

@identity_loaded.connect_via(app)
def on_identity_loaded(sender, identity):
    # Set the identity user object
    identity.user = g.user

    # Add the UserNeed to the identity
    if hasattr(g.user, 'id'):
        identity.provides.add(UserNeed(g.user.id))

    # Assuming the User model has a list of roles, update the
    # identity with the roles that the user provides
    # Currently roles does not get populated
    if hasattr(g.user, 'roles'):
        for role in g.user.roles:
            identity.provides.add(RoleNeed(role.name))

    # Assuming the User model has a list of resumes the user
    # has authored, add the needs to the identity
    if type(identity) != AnonymousIdentity:
        creator = Person.objects.get(email=g.user.email)
        resumes = resume_model.Resume.objects.get(parent=creator)
        for resume in resumes:
            identity.provides.add(EditResumeNeed(unicode(resume.id)))