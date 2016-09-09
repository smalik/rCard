"""
review.py: Sets up the review page, where all resumes that
have been pushed by an external user are visible and can
be approved/rejected. Creates this in the "Review" page

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
from plytos.views.get import (person_with_username, 
    resume_with_id, comments_with_id)

def get_pairs(edit, original):
    edit_ids     = [item._id for item in edit]
    original_ids = [item._id for item in original]
    new_fields   = list(range(len(edit_ids)))

    pairs = []
    for item in range(len(original_ids)):
        original_id = original_ids[item]
        if original_id in edit_ids:
            copy_index = edit_ids.index(original_id)
            pairs.append([item, copy_index])
            new_fields.remove(copy_index)
        else: pairs.append([item, None])

    for field in new_fields:
        pairs.append([None, field])
    return pairs

def save_edit(request, _id, is_new=True):
    dbUser = person_with_username(g.user.username)
    values = request.form["location"].split("_")
    form_type = values[0]
    try:
        which_orig_form = int(values[1])
    except: which_orig_form = None
    try:
        which_edit_form = int(values[2])
    except: which_edit_form = None

    # case where only accepting a particular field
    if request.form["submit"] == "accept":
        which_field = values[3]
        dbUser.internal_accept(_id, form_type, which_orig_form, 
            which_edit_form, which_field, is_new)

    # case where accepting the whole revision
    else: dbUser.overall_accept(_id, form_type, which_orig_form,
        which_edit_form, is_new)

def populate_comments(resume):
    forms = ['work', 'volunteer', 'education', 'awards', 'skills', 
        'publications', 'interests', 'languages']

    comments = {}
    for form in forms:
        comments[form] = [comments_with_id(comment, form) for
            comment in resume[form].comments]
    return comments

def review_view(_id, forms):
    dbUser = person_with_username(g.user.username)
    current_edit = resume_with_id(_id)
    working_resume = resume_with_id(current_edit.parent_resume)
    comments = populate_comments(current_edit)

    context = {}
    for field in forms:
        context[field] = get_pairs(current_edit[field].items, 
            working_resume[field].items)

    return render_template('resumes/review.html',
        edit=current_edit, orig=working_resume, forms=forms, 
        comments=comments, **context)

class ReviewView(View):
    #Also need a decorator to verify this is the owner of resume
    decorators = [login_required]

    def get(self, _id):
        forms = ['work', 'volunteer', 'education', 'awards', 'skills', 
            'publications', 'interests', 'languages']
        return review_view(_id, forms)

    def post(self, _id):
        save_edit(request, _id)
        return redirect(url_for('resume_app.review', slug=str(_id)))

    def dispatch_request(self, slug):
        _id = ObjectId(slug)

        if request.method.lower() == 'get':
            return self.get(_id)
        if request.method.lower() == 'post':
            return self.post(_id)
        return "Improper method used: {}".format(request.method)

class PublishView(View):
    #Also need a decorator to verify this is the owner of resume
    decorators = [login_required]

    def get(self, _id):
        dbUser = person_with_username(g.user.username)
        dbUser.resume_publish(_id)
        return redirect(url_for('resume_app.list', view='edit'))

    def dispatch_request(self, slug):
        _id = ObjectId(slug)
        if request.method.lower() == 'get':
            return self.get(_id)
        return "Improper method used: {}".format(request.method)

def setup_review(resume_app):
    # used for accepting/reviewing edits that have been proposed
    resume_app.add_url_rule('/review/<slug>', 
        view_func=ReviewView.as_view('review'), methods=['GET', 'POST'])
    resume_app.add_url_rule('/publish/<slug>', 
        view_func=PublishView.as_view('publish'), methods=['GET'])