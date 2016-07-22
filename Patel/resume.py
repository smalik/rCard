from flask import (Blueprint, render_template, request, redirect, 
    url_for, g, abort, session)
from flask.views import View
from flask.ext.mongoengine.wtf import model_form
from flask.ext.login import current_user
from flask.ext.principal import (identity_loaded, Permission, RoleNeed,
    UserNeed, AnonymousIdentity, Identity)
from bson.objectid import ObjectId

from decorators import login_required
import json
from collections import namedtuple
from functools import partial
import time

import resumes, comments
from app import app
from models import Resume, Comment, CommentsPerSection, Person, ToDosPerSection
from forms import ResumeForm, CommentForm

ResumeNeed = namedtuple('resume', ['method', 'value'])
EditResumeNeed = partial(ResumeNeed, 'edit')

resume_app = Blueprint('resume_app', __name__, template_folder='templates')
class EditResumePermission(Permission):
    def __init__(self, resume_id):
        need = EditResumeNeed(unicode(resume_id))
        super(EditResumePermission, self).__init__(need)

def _form_to_dict(form):
    form_dict = {}
    for field in form:
        form_dict[field.name] = field._value().split(',')
    return form_dict

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
    
    #if not isinstance(current_user._get_current_object(), AnonymousUser):
    if type(identity) != AnonymousIdentity:
        creator = Person.objects.get(email=g.user.email)
        resumes = Resume.objects.get(parent=creator)
        for resume in resumes:
            identity.provides.add(EditResumeNeed(unicode(resume.id)))

class ListView(View):
    decorators = [login_required]

    def get(self):
        # Listview only show particular user's resume
        creator = Person.objects.get_or_404(email=g.user.email)
        return render_template('resumes/list.html', 
            resumes=creator.working_resumes)

    def dispatch_request(self):
        if request.method.lower() == 'get':
            return self.get()
        return "Improper method used: {}".format(request.method)

class DetailView(View):
    decorators = [login_required]
    CHOICES = ((1, "experience"), (2, "education"), 
        (3, "activities"), (4, "honors"), (5, "publication"))
    form = model_form(Comment, exclude=['created_at'])

    #These two should be one top method
    @classmethod
    def init_comments(self, resume):
        if not resume.comments_per_section:
            for choice in self.CHOICES:
                comment_per_tag = CommentsPerSection()
                comment_per_tag.num_comments = 0
                comment_per_tag.index_num = choice[0]
                comment_per_tag.section_name = choice[1]
                resume.comments_per_section = comment_per_tag

    @classmethod
    def init_todos(self, resume):
        if not resume.todos_per_section:
            for choice in self.CHOICES:
                todos_per_tag = ToDosPerSection()
                todos_per_tag.num_todos = 0
                todos_per_tag.index_num = choice[0]
                todos_per_tag.section_name = choice[1]
                resume.todos_per_section = todos_per_tag

    def get_context(self, slug=None):
        form = self.form()
        resume = Resume.objects.get_or_404(slug=slug)
        context = {
            "resume": resume,
            "form": form,
            "choices": self.CHOICES
        }
        return context

    def get(self, slug):
        context = self.get_context(slug)

        # When this is passed in render template is smart enough
        # to have post, form available in the template context
        return render_template('resumes/detail.html', **context)

    def post(self, slug):
        context = self.get_context(slug)
        form = context.get('form')

        if form.validate():
            comment = Comment()
            form.populate_obj(comment)

            resume = context.get('resume')
            resume.comments.append(comment)

            # Intitialize the tags counter for sections
            # Looping from fields possible 
            # http://stackoverflow.com/questions/8586738/get-required-fields-from-document-in-mongoengine
            self.init_comments(resume)
            self.init_todos(resume)

            for tag in comment.tags:
                resume.comments_per_section[tag-1].num_comments += 1

            resume.parent.save()

            return redirect(url_for('resume_app.detail', slug=slug))
        return render_template('resumes/detail.html', **context)

    def dispatch_request(self, slug):
        if request.method.lower() == 'get':
            return self.get(slug)
        elif request.method.lower() == 'post':
            return self.post(slug)
        return "Improper method used: {}".format(request.method)

class CreateView(View):
    decorators = [login_required]
    CHOICES = ((1, "experience"), (2, "education"), 
        (3, "activities"), (4, "honors"), (5, "publication"))
    ResumeForm = model_form(Resume, exclude=['created_at', 'last_updated',
        'comments', 'slug', 'user', 'comments', 'comments_per_section', 
        'todos_per_section'])
    #ActivityForm = model_form(ActivityItem, exclude=['comments'])

    def get_context(self, slug=None):
        if slug:
            resume = Resume.objects.get_or_404(slug=slug)
            permission = EditResumePermission(unicode(resume.id))
            #permission = Permission(UserNeed(g.user.id))
            g.identity.provides.add(EditResumeNeed(unicode(resume.id)))

            #FIXME: At this point, permission.can does not allow access
            if permission.can():
                if request.method.lower() == 'post':
                    form = ResumeForm(request.form, initial=resume._data)
                else:
                    form = ResumeForm(obj=resume)
            abort(403)
        else:
            resume = Resume()
            slug = str(ObjectId())
            form = ResumeForm()

        context = {
            "resume": resume,
            "form": form,
            "create": slug is None
        }
        return context

    def get(self, slug):
        context = self.get_context(slug)
        return render_template('resumes/create.html', **context)

    def post(self, slug):
        context = self.get_context(slug)
        form = context.get('form')

        if form.validate():
            form_dict = _form_to_dict(form)
            creator = Person.objects.get_or_404(email=g.user.email)
            
            resume = context.get('resume')
            form.populate_obj(resume)

            experience = resumes.Experience(
                _id = ObjectId(),
                items = form_dict['experience'],
                comments = []
            )
            volunteer = resumes.Volunteer(
                _id = ObjectId(),
                items = form_dict['volunteer'],
                comments = []
            )
            education = resumes.Education(
                _id = ObjectId(),
                items = form_dict['education'],
                comments = []
            )
            awards = resumes.Awards(
                _id = ObjectId(),
                items = form_dict['awards'],
                comments = []
            )
            pubs = resumes.Publications(
                _id = ObjectId(),
                items = form_dict['pubs'],
                comments = []
            )
            interests = resumes.Interests(
                _id = ObjectId(),
                items = form_dict['interests'],
                comments = []
            )
            languages = resumes.Languages(
                _id = ObjectId(),
                items = form_dict['languages'],
                comments = []
            )
            skills = resumes.Skills(
                _id = ObjectId(),
                items = form_dict['skills'],
                comments = []
            )

            resume._id = ObjectId()
            resume.slug = str(resume._id)
            resume.experience = experience
            resume.volunteer = volunteer
            resume.education = education
            resume.awards = awards
            resume.pubs = pubs
            resume.interests = interests
            resume.languages = languages
            resume.skills = skills
            
            resume.parent_user = creator.username
            resume.version = None
            resume.num_edits = 0

            resume.save()

            creator.working_resumes.append(resume)
            creator.save()

            return redirect(url_for('resume_app.list'))
        return render_template('resumes/create.html', **context)

    def dispatch_request(self, slug):
        if request.method.lower() == 'get':
            return self.get(slug)
        elif request.method.lower() == 'post':
            return self.post(slug)
        return "Improper method used: {}".format(request.method)

class VersionControlView(View):
    #Also need a decorator to verify this is the owner of resume
    decorators = [login_required]

    def get(self):
        dbUser = resumes.Person.objects.get_or_404(
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
        dbUser = resumes.Person.objects.get_or_404(
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
        dbUser = resumes.Person.objects.get_or_404(
            username=g.user.username)
        resume_index = dbUser.which_contain_doc(
            dbUser.editing_resumes, slug)

        resume = dbUser.editing_resumes[resume_index]
        
        form = ResumeForm()
        comment_form = CommentForm()
        context = {
            "resume": resume,
            "form": form,
            "comment_form": comment_form
        }
        return context

    def get(self, slug):
        context = self.get_context(slug)

        resume = context.get('resume')
        form = context.get('form')
        comment_form = context.get('comment_form')

        for field in _form_to_dict(form):
            if field in resume:
                form[field].data = ", ".join(resume[field].items)

        return render_template('resumes/edit.html', 
            form=form, comment_form=comment_form)

    def post(self, slug):
        context = self.get_context(slug)
        resume = context.get('resume')
        dbUser = resumes.Person.objects.get_or_404(
            username=g.user.username)
        if "comment" in request.form:
            comment_form = context.get('comment_form')

            comment = resumes.Comment()
            comment._id = ObjectId()
            comment.author_user = dbUser.username
            # comment.createDt = time.gmtime(time.time())
            comment.topic = comment_form['topic'].data
            comment.section = comment_form['section'].data
            comment.upvote = 0
            comment.downvote = 0
            comment.payload = comment_form['payload'].data
            comment.save()

            # resume.comments = [comment]
            resume.comments = []
            resume.comments.append(comment)
            print(resume.comments)
            # resume.comments.save()
            resume.save()
        else:
            form = context.get('form')
            if form.validate():
                for field in _form_to_dict(form):
                    if field in resume:
                        resume[field].items = form[field].data.split(",")
            resume.save()

            if request.form['submit'] == 'save':
                dbUser.resume_save(resume)
            elif request.form['submit'] == 'push':
                dbUser.resume_submit(resume)

            parent = resumes.Person.objects.get_or_404(
                username=resume.parent_user)
        return render_template('resumes/list.html', 
            resumes=dbUser.editing_resumes)

    def dispatch_request(self, slug):
        if request.method.lower() == 'get':
            return self.get(slug)
        if request.method.lower() == 'post':
            return self.post(slug)
        return "Improper method used: {}".format(request.method)

class ReviewView(View):
    #Also need a decorator to verify this is the owner of resume
    decorators = [login_required]

    def get(self):
        session['slug'] = None
        dbUser = resumes.Person.objects.get_or_404(
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
        dbUser = resumes.Person.objects.get_or_404(
            username=g.user.username)
        if 'Publish ' in slug:
            dbUser.resume_publish(slug.replace('Publish ',''))
            return redirect(url_for('resume_app.review'))

        works = dbUser.working_resumes
        edits = dbUser.current_edits

        working_resume = works[dbUser.which_contain_doc(works, slug)]
        current_edit = edits[dbUser.which_contain_doc(edits, slug)]

        edit_fields = ['experience', 'volunteer', 'education', 
            'skills', 'awards', 'pubs', 'interests', 'languages']
        return render_template('resumes/review.html',
            edit=current_edit, orig=working_resume, fields=edit_fields)

    def post(self, slug):
        dbUser = resumes.Person.objects.get_or_404(
            username=g.user.username)
        if 'submit' in request.form:
            if request.form['submit'] == 'accept':
                field = request.form['field']
                edit_value = request.form['edit']
                dbUser.resume_accept(slug, field, edit_value)
            return redirect(url_for('resume_app.review'))

    def dispatch_request(self, slug):
        session['slug'] = slug
        if request.method.lower() == 'get':
            return self.get(session['slug'])
        if request.method.lower() == 'post':
            return self.post(session['slug'])
        return "Improper method used: {}".format(request.method)

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

class TodoView(View):
    #Also need a decorator to verify this is the owner of resume
    decorators = [login_required]

    def post(self, slug=None):
        x = json.loads(request.data)
        # This is a limitation of logic to generate slugs
        # should really generate a unique slug
        resume = Resume.objects.get_or_404(slug=x['slug'].replace("%20", " "))

        for section in x['sections']:
            for todo in resume.todos_per_section:
                if todo.section_name.lower() == section["section_name"].lower():
                    todo.num_todos = section["value"]
        
        resume.parent.save()
        return "200"

    def dispatch_request(self, slug):
        if request.method.lower() == 'post':
            return self.post(slug)
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

resume_app.add_url_rule('/', view_func=ListView.as_view('list'), 
    methods=['GET', 'POST'])
resume_app.add_url_rule('/<slug>', view_func=DetailView.as_view('detail'), 
    methods=['GET', 'POST'])

#defaults added otherwise create crashes as get takes two params
resume_app.add_url_rule('/create', defaults={'slug': None},
    view_func=CreateView.as_view('create'), methods=['GET', 'POST'])
resume_app.add_url_rule('/<slug>/edit', view_func=CreateView.as_view('edit'), 
    methods=['GET', 'POST'])
resume_app.add_url_rule('/todos', view_func=TodoView.as_view('todos'), 
    methods=['POST'])

# used to make edits to others' resumes (search/edit/default pages)
resume_app.add_url_rule('/find', view_func=FindView.as_view('find'), 
    methods=['GET', 'POST'])
resume_app.add_url_rule('/edits', 
    view_func=VersionControlView.as_view('version'), methods=['GET', 'POST'])
resume_app.add_url_rule('/edit/<slug>', 
    view_func=EditView.as_view('edit_external'), methods=['GET', 'POST'])

# used for accepting/reviewing edits that have been proposed
resume_app.add_url_rule('/review', view_func=ReviewView.as_view('review'), 
    methods=['GET', 'POST'])
resume_app.add_url_rule('/review/<slug>', 
    view_func=OneReviewView.as_view('review_single'), methods=['GET', 'POST'])

# for viewing the finalized resumes
resume_app.add_url_rule('/final', view_func=FinalView.as_view('final'), 
    methods=['GET'])