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

from plytos.decorators import login_required
from plytos.models.person import Person

# Fields that hold multiple values in a single slot
MULTIPLE = ["highlights", "skills", "courses", 
    "pubs", "interests", "languages"]

class ReviewView(View):
    #Also need a decorator to verify this is the owner of resume
    decorators = [login_required]

    def get(self):
        session['slug'] = None
        dbUser = Person.objects.get_or_404(
            username=g.user.username)
        sorted_edits = dbUser.get_sorted_edits()
        return render_template('resumes/list_review.html',
            resumes=sorted_edits)

    def post(self):
        slug = list(request.form.keys())[0]
        return redirect(url_for('resume_app.review_single',
            slug=slug))

    def dispatch_request(self):
        if request.method.lower() == 'get':
            return self.get()
        if request.method.lower() == 'post':
            return self.post()
        return "Improper method used: {}".format(request.method)

class OneReviewView(View):
    #Also need a decorator to verify this is the owner of resume
    decorators = [login_required]

    def get(self, slug):
        dbUser = Person.objects.get_or_404(
            username=g.user.username)
        if 'Publish ' in slug:
            dbUser.resume_publish(slug.replace('Publish ',''))
            return redirect(url_for('resume_app.review'))

        works = dbUser.working_resumes
        edits = dbUser.current_edits

        working_resume = works[dbUser.which_contain_doc(works, slug)]
        current_edit = edits[dbUser.which_contain_doc(edits, slug)]

        lists = ['experience', 'volunteer', 'education', 'awards']
        edit_fields = ['skills', 'pubs', 'interests', 'languages']
        return render_template('resumes/review.html',
            edit=current_edit, orig=working_resume, 
            fields=edit_fields, lists=lists)

    def post(self, slug):
        dbUser = Person.objects.get_or_404(
            username=g.user.username)
        if 'submit' in request.form:
            if request.form['submit'] == 'accept':
                field = request.form['field']
                edit_value = request.form['edit']
                dbUser.resume_accept(slug, field, edit_value)
            elif request.form['submit'] == 'accept_list':
                for field in request.form.keys():
                    separated = field.split("/")

                    if "edit" in separated and len(request.form[field].strip()) != 0:
                        form_type = separated[1]
                        which_form = int(separated[2])
                        field_name = separated[3]

                        edit_val = request.form[field]
                        
                        if field_name != "_id" and edit_val != "None":
                            if field_name in MULTIPLE:
                                edit_val = edit_val.split()

                            dbUser.internal_accept(slug, form_type, 
                                which_form, field_name, edit_val)
            return redirect(url_for('resume_app.review'))

    def dispatch_request(self, slug):
        session['slug'] = slug
        if request.method.lower() == 'get':
            return self.get(session['slug'])
        if request.method.lower() == 'post':
            return self.post(session['slug'])
        return "Improper method used: {}".format(request.method)

# both the below are pulled (implements git diff) from
# https://en.wikibooks.org/wiki/Algorithm_Implementation/Strings/
# Longest_common_subsequence
def LCS(X, Y):
    m = len(X)
    n = len(Y)
    # An (m+1) times (n+1) matrix
    C = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m+1):
        for j in range(1, n+1):
            if X[i-1] == Y[j-1]: 
                C[i][j] = C[i-1][j-1] + 1
            else:
                C[i][j] = max(C[i][j-1], C[i-1][j])
    return C

def get_diff(C, X, Y, i, j):
    if i > 0 and j > 0 and X[i-1] == Y[j-1]:
        return get_diff(C, X, Y, i-1, j-1) + "  " + X[i-1]
    else:
        if j > 0 and (i == 0 or C[i][j-1] >= C[i-1][j]):
            return get_diff(C, X, Y, i, j-1) +  "+ " + Y[j-1]
        elif i > 0 and (j == 0 or C[i][j-1] < C[i-1][j]):
            return get_diff(C, X, Y, i-1, j) + "- " + X[i-1]

def setup_review(resume_app):
    # used for accepting/reviewing edits that have been proposed
    resume_app.add_url_rule('/review', view_func=ReviewView.as_view('review'), 
        methods=['GET', 'POST'])
    resume_app.add_url_rule('/review/<slug>', 
        view_func=OneReviewView.as_view('review_single'), methods=['GET', 'POST'])