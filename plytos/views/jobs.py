"""
jobs.py: Sets up the jobs page, where all the job posting will be
visible and populated

__author__ = "Yash Patel"
__copyright__ = "Copyright 2016, Plytos Inc."

__license__ = "Free/Open"
__version__ = "1.0.0"
__maintainer__ = "Yash Patel"
__email__ = "ypatel@princeton.edu"
"""

from flask import Blueprint, render_template, request, redirect, url_for

from flask import (render_template, request, redirect, 
    url_for, g, abort, session)
from flask.views import View

from bson.objectid import ObjectId

from plytos.decorators import login_required
from plytos.models.person import Person
from plytos.views.get import (person_with_username, resume_with_id)
from plytos.views.personal import new_resume

def get_jobs():
    return ["TEST JOB 1"]

class JobsView(View):
    decorators = [login_required]
    def get(self):
        return render_template('jobs/jobs.html', jobs=get_jobs())

    def dispatch_request(self):
        if request.method.lower() == 'get':
            return self.get()
        return "Improper method used: {}".format(request.method)

class ApplyView(View):
    decorators = [login_required]
    def get(self):
        dbUser = person_with_username(g.user.username)
        return render_template('jobs/apply.html', 
            resumes=dbUser.final_resumes)

    def dispatch_request(self):
        if request.method.lower() == 'get':
            return self.get()
        return "Improper method used: {}".format(request.method)

class CreateView(View):
    decorators = [login_required]
    def get(self):
        dbUser = person_with_username(g.user.username)
        forms  = ["work", "volunteer", "education", "awards", 
        	"publications", "interests", "languages", "skills"]

        create_resume = new_resume(ObjectId())
        for resume_id in dbUser.final_resumes:
            resume = resume_with_id(resume_id) 
            for field in forms:
            	create_resume[field].items += resume[field].items
        create_resume.parent_resume = None
        create_resume.switch_db("resumes")
        create_resume.save()

        return redirect(url_for('resume_app.revise', edit='edit',
        	slug=str(create_resume._id)))

    def dispatch_request(self):
        if request.method.lower() == 'get':
            return self.get()
        return "Improper method used: {}".format(request.method)

def setup_jobs(jobs_app):
    # for viewing the finalized resumes
    jobs_app.add_url_rule('/', 
        view_func=JobsView.as_view('jobs'), methods=['GET'])
    jobs_app.add_url_rule('/apply', 
        view_func=ApplyView.as_view('apply'), methods=['GET'])
    jobs_app.add_url_rule('/create', 
        view_func=CreateView.as_view('create'), methods=['GET'])

jobs_app = Blueprint('jobs_app', __name__, template_folder='templates')
setup_jobs(jobs_app)