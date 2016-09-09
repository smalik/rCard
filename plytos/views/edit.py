"""
edit.py: Sets up the edit page functionality, including the
page to create individual edits, list all the editing documents,
and adding a new document to edit. Creates these in the
"Find" and "Edit" pages

__author__ = "Yash Patel"
__copyright__ = "Copyright 2016, Plytos Inc."

__license__ = "Free/Open"
__version__ = "1.0.0"
__maintainer__ = "Yash Patel"
__email__ = "ypatel@princeton.edu"
"""

from flask import (render_template, request, redirect, 
    url_for, g, abort, session)
from flask.views import View
from mongoengine.context_managers import switch_db

from bson.objectid import ObjectId

from plytos.models.comments import Comment, CommentsPerSection
from plytos.models.todo import ToDosPerSection
from plytos.decorators import login_required
from plytos.forms import (ResumeForm, CommentForm, WorkForm, VolunteerForm, 
    EducationForm, AwardForm)

from plytos.models.resume import Resume
from plytos.models.person import Person
from plytos.views.get import (person_with_username, 
    resume_with_id, resume_with_ids)

class FindView(View):
    #Also need a decorator to verify this is the owner of resume
    decorators = [login_required]

    def get(self):
        return render_template('resumes/find.html')

    def post(self):
        dbUser = person_with_username(g.user.username)
        if "resume_id" in request.form:
            resume = resume_with_id(ObjectId(request.form["resume_id"]))
            dbUser.resume_fork(resume)
        return redirect(url_for('resume_app.list', view='revise'))

    def dispatch_request(self):
        if request.method.lower() == 'get':
            return self.get()
        if request.method.lower() == 'post':
            return self.post()
        return "Improper method used: {}".format(request.method)

def setup_edit(resume_app):
    # used to make edits to others' resumes (search/edit/default pages)
    resume_app.add_url_rule('/find', view_func=FindView.as_view('find'), 
        methods=['GET', 'POST'])