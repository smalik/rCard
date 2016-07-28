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

from bson.objectid import ObjectId

from plytos.models.comments import Comment, CommentsPerSection, ToDosPerSection
from plytos.decorators import login_required
from plytos.forms import (ResumeForm, CommentForm, WorkForm, VolunteerForm, 
    EducationForm, AwardForm)

from plytos.models.resume import Resume
from plytos.models.person import Person

# Fields that hold multiple values in a single slot
MULTIPLE = ["highlights", "skills", "courses", 
    "pubs", "interests", "languages"]

def _form_to_dict(form):
    form_dict = {}
    for field in form:
        form_dict[field.name] = field._value()
    return form_dict

class VersionControlView(View):
    #Also need a decorator to verify this is the owner of resume
    decorators = [login_required]

    def get(self):
        dbUser = Person.objects.get_or_404(
            username=g.user.username)
        return render_template('resumes/list_edit.html', 
            resumes=dbUser.editing_resumes)

    def post(self):
        return redirect(url_for('resume_app.find'))

    def dispatch_request(self):
        if request.method.lower() == 'get':
            return self.get()
        if request.method.lower() == 'post':
            return self.post()
        return "Improper method used: {}".format(request.method)

class FindView(View):
    #Also need a decorator to verify this is the owner of resume
    decorators = [login_required]

    def get(self):
        return render_template('resumes/find.html')

    def post(self):
        dbUser = Person.objects.get_or_404(
            username=g.user.username)
        if "resume_id" in request.form:
            resume = Resume.objects.get_or_404(
                slug=request.form["resume_id"])
            dbUser.resume_fork(resume)
        return redirect(url_for('resume_app.version'))

    def dispatch_request(self):
        if request.method.lower() == 'get':
            return self.get()
        if request.method.lower() == 'post':
            return self.post()
        return "Improper method used: {}".format(request.method)

class EditView(View):
    #Also need a decorator to verify this is the owner of resume
    decorators = [login_required]

    def get_context(self, slug):
        dbUser = Person.objects.get_or_404(
            username=g.user.username)
        resume_index = dbUser.which_contain_doc(
            dbUser.editing_resumes, slug)

        resume = dbUser.editing_resumes[resume_index]
        experience = resume.experience.items
        volunteer = resume.volunteer.items
        education = resume.education.items
        awards = resume.awards.items
        
        form = ResumeForm()
        comment_form = CommentForm()
        context = {
            "resume": resume,
            "experience": experience,
            "volunteer": volunteer,
            "education": education,
            "awards": awards,

            "form": form,
            "comment_form": comment_form
        }
        return context

    def get(self, slug):
        context = self.get_context(slug)

        resume = context.get('resume')
        experience = context.get('experience')
        volunteer = context.get('volunteer')
        education = context.get('education')
        awards = context.get('awards')

        form = context.get('form')
        comment_form = context.get('comment_form')

        for field in _form_to_dict(form):
            if field in resume:
                form[field].data = ", ".join(resume[field].items)

        return render_template('resumes/edit.html', 
            slug=slug, form=form, comment_form=comment_form,
            experience=experience, volunteer=volunteer, 
            education=education, awards=awards)

    def post(self, slug):
        context = self.get_context(slug)
        resume = context.get('resume')
        dbUser = Person.objects.get_or_404(
            username=g.user.username)
        if "comment" in request.form:
            comment_form = context.get('comment_form')

            comment = Comment()
            comment._id = ObjectId()
            comment.author_user = dbUser.username
            # comment.createDt = time.gmtime(time.time())
            comment.topic = comment_form['topic'].data
            comment.section = comment_form['section'].data
            comment.upvote = 0
            comment.downvote = 0
            comment.payload = comment_form['payload'].data

            resume.comments.append(comment)
            resume.save()
        else:
            form = context.get('form')
            if form.validate():
                for field in _form_to_dict(form):
                    if field in resume:
                        if field in MULTIPLE:
                            resume[field].items = form[field].data.split(",")
                        else: resume[field].items = form[field].data
            resume.save()

            if request.form['submit'] == 'save':
                dbUser.resume_save(resume)
            elif request.form['submit'] == 'push':
                dbUser.resume_submit(resume)
        return render_template('resumes/list.html', 
            resumes=dbUser.editing_resumes)

    def dispatch_request(self, slug):
        if request.method.lower() == 'get':
            return self.get(slug)
        if request.method.lower() == 'post':
            return self.post(slug)
        return "Improper method used: {}".format(request.method)

class IndivEditView(View):
    #Also need a decorator to verify this is the owner of resume
    decorators = [login_required]

    def get_context(self, slug):
        dbUser = Person.objects.get_or_404(
            username=g.user.username)
        resume_index = dbUser.which_contain_doc(
            dbUser.editing_resumes, slug)
        resume = dbUser.editing_resumes[resume_index]

        context = {
            "resume": resume,

            "form": ResumeForm(),
            "comment": CommentForm(),
            "experience": WorkForm(),
            "volunteer": VolunteerForm(),
            "education": EducationForm(),
            "awards": AwardForm(),
        }
        return context

    # /indiv_edit/<slug>/<collection>/<item>
    def get(self, slug, collection, item):
        context = self.get_context(slug)
        dbUser = Person.objects.get_or_404(
            username=g.user.username)
        resume_index = dbUser.which_contain_doc(
            dbUser.editing_resumes, slug)

        resume = context.get("resume")
        comment_form = context.get("comment")

        form = context.get(collection)
        orig_form = resume[collection].items[item]

        for field in _form_to_dict(form):
            if field in orig_form:
                if field in MULTIPLE:
                    form[field].data = ", ".join(orig_form[field])
                else: 
                    form[field].data = orig_form[field]

        return render_template("resumes/indiv_edit.html", 
            form=form, comment_form=comment_form, slug=slug)

    def post(self, slug, collection, item):
        context = self.get_context(slug)
        resume = context.get('resume')
        dbUser = Person.objects.get_or_404(
            username=g.user.username)
        
        if "comment" in request.form:
            comment_form = context.get('comment')

            comment = Comment()
            comment._id = ObjectId()
            comment.author_user = dbUser.username
            # comment.createDt = time.gmtime(time.time())
            comment.topic = comment_form['topic'].data
            comment.section = comment_form['section'].data
            comment.upvote = 0
            comment.downvote = 0
            comment.payload = comment_form['payload'].data
            
            # resume.comments = [comment]
            resume[collection].comments.append(comment)
            resume.save()
        
        else:
            edit_section = resume[collection].items[item]
            form = context.get(collection)
            if form.validate():
                for field in _form_to_dict(form):
                    if field in edit_section:
                        if field in MULTIPLE:
                            edit_section[field] = form[field].data.split(",")
                        else: edit_section[field] = form[field].data
            resume.save()

        dbUser.resume_save(resume)
        return redirect(url_for("resume_app.edit_external", slug=slug))

    def dispatch_request(self, slug, collection, item):
        if request.method.lower() == 'get':
            return self.get(slug, collection, int(item))
        if request.method.lower() == 'post':
            return self.post(slug, collection, int(item))
        return "Improper method used: {}".format(request.method)

def setup_edit(resume_app):
    # used to make edits to others' resumes (search/edit/default pages)
    resume_app.add_url_rule('/find', view_func=FindView.as_view('find'), 
        methods=['GET', 'POST'])
    resume_app.add_url_rule('/edits', 
        view_func=VersionControlView.as_view('version'), methods=['GET', 'POST'])
    resume_app.add_url_rule('/edit/<slug>', 
        view_func=EditView.as_view('edit_external'), methods=['GET', 'POST'])

    # edit for any one of: experience, skills, education, awards 
    # (i.e. all the classes which are lists of separate models)
    resume_app.add_url_rule('/indiv_edit/<slug>/<collection>/<item>', 
        view_func=IndivEditView.as_view('indiv_edit'), methods=['GET', 'POST'])