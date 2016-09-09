"""
history.py: Sets up the history page, where you can traverse the
revision history of particular resumes and revert changes.

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

from bson.objectid import ObjectId

from plytos.decorators import login_required
from plytos.models.person import Person

from plytos.views.get import (person_with_username, resume_with_id,
    resume_with_ids)
from plytos.views.review import save_edit, review_view

class RevertView(View):
    decorators = [login_required]
    def get(self, _id, field):
        return review_view(_id, forms=[field])

    def post(self, _id):
        save_edit(request, _id, is_new=False)
        return redirect(url_for('resume_app.list', view='history'))

    def dispatch_request(self, slug, field):
        _id = ObjectId(slug)
        if request.method.lower() == 'get':
            return self.get(_id, field)
        elif request.method.lower() == 'post':
            return self.post(_id)
        return "Improper method used: {}".format(request.method)

def setup_history(resume_app):
    # for viewing the finalized resumes
    resume_app.add_url_rule('/history/<field>/<slug>', 
        view_func=RevertView.as_view('revert'), methods=['GET', 'POST'])