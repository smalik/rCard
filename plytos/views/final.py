"""
final.py: Sets up the final page view, where all the published
resumes are visible (those that have been approved from the
Review tab)

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

from plytos.decorators import login_required
from plytos.models.person import Person

class FinalView(View):
    decorators = [login_required]

    def get(self):
        # Listview only show particular user's resume
        creator = Person.objects.get_or_404(email=g.user.email)
        return render_template('resumes/list.html', 
            resumes=creator.final_resumes)

    def dispatch_request(self):
        if request.method.lower() == 'get':
            return self.get()
        return "Improper method used: {}".format(request.method)

def setup_final(resume_app):
    # for viewing the finalized resumes
    resume_app.add_url_rule('/final', view_func=FinalView.as_view('final'), 
        methods=['GET'])