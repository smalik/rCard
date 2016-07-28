"""
self_resume.py: Sets up both the "View" and "Create" pages, where
users can create resumes for their personal account.

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

from flask.ext.mongoengine.wtf import model_form
from flask.ext.login import current_user
from flask.ext.principal import Permission, UserNeed

from bson.objectid import ObjectId

from plytos.decorators import login_required
from plytos.models.comments import Comment, CommentsPerSection, ToDosPerSection
from plytos.forms import (ResumeForm, CommentForm, WorkForm, VolunteerForm, 
    EducationForm, AwardForm)

import plytos.models.resume as resume_model
from plytos.models.person import Person

def _form_to_dict(form):
    form_dict = {}
    for field in form:
        form_dict[field.name] = field._value()
    return form_dict

class EditResumePermission(Permission):
    def __init__(self, resume_id):
        need = EditResumeNeed(unicode(resume_id))
        super(EditResumePermission, self).__init__(need)

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
        resume = resume_model.Resume.objects.get_or_404(slug=slug)
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
            # http://stackoverflow.com/questions/8586738/get-required-fields-
            # from-document-in-mongoengine
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
    ResumeForm = model_form(resume_model.Resume, exclude=['created_at',
        'last_updated', 'comments', 'slug', 'user', 'comments', 
        'comments_per_section', 'todos_per_section'])

    work_items = []
    volunteer_items = []
    education_items = []
    award_items = []

    def get_time(self, val):
        try:
            return datetime.strptime(val, '%d/%m/%Y')
        except: return None

    def reset(self):
        self.work_items = []
        self.volunteer_items = []
        self.education_items = []
        self.award_items = []

    def get_context(self, slug=None):
        if slug:
            resume = resume_model.Resume.objects.get_or_404(slug=slug)
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
            resume = resume_model.Resume()
            slug = str(ObjectId())
            
            form = ResumeForm()
            work_form = WorkForm()
            volunteer_form = VolunteerForm()
            education_form = EducationForm()
            award_form = AwardForm()

        context = {
            "resume": resume,
            "form": form,
            "work_form": work_form,
            "volunteer_form": volunteer_form,
            "education_form": education_form,
            "award_form": award_form,
            "create": slug is None
        }
        return context

    def get(self, slug):
        context = self.get_context(slug)
        return render_template('resumes/create.html', **context)

    def post(self, slug):
        context = self.get_context(slug)
        submit_type = request.form['submit'].split()[-1].strip().lower()
        
        form = context.get('form')
        work_form = context.get("work_form")
        volunteer_form = context.get("volunteer_form")
        education_form = context.get("education_form")
        award_form = context.get("award_form")

        if submit_type == 'work' and \
            work_form.validate():
            form_dict = _form_to_dict(work_form)

            start_date = self.get_time(form_dict["startDt"])
            end_date = self.get_time(form_dict["endDt"])

            work = resume_model.WorkItem(
                company=form_dict["company"],
                startDt=start_date,
                endDt=end_date,
                position=form_dict["position"],
                url=form_dict["url"],
                impact=form_dict["impact"],

                highlights=form_dict["highlights"].split(","),
                skills=form_dict["skills"].split(",")
            )
            self.work_items.append(work)

        elif submit_type == 'volunteer' and \
            volunteer_form.validate():
            form_dict = _form_to_dict(volunteer_form)

            start_date = self.get_time(form_dict["startDt"])
            end_date = self.get_time(form_dict["endDt"])

            volunteer = resume_model.VolunteerItem(
                org=form_dict["org"],
                title=form_dict["title"],
                startDt=start_date,
                endDt=end_date,
                url=form_dict["url"],
                impact=form_dict["impact"],

                highlights=form_dict["highlights"].split(",")
            )
            self.volunteer_items.append(volunteer)

        elif submit_type == 'education' and \
            education_form.validate():
            form_dict = _form_to_dict(education_form)

            start_date = self.get_time(form_dict["startDt"])
            grad_date = self.get_time(form_dict["gradDt"])

            education = resume_model.EducationItem(
                school=form_dict["school"],
                degree=form_dict["degree"],
                major=form_dict["major"],
                startDt=start_date,
                gradDt=grad_date,
                gpa=form_dict["gpa"],

                courses=form_dict["courses"].split(",")
            )
            self.education_items.append(education)

        elif submit_type == 'award' and \
            award_form.validate():
            form_dict = _form_to_dict(award_form)

            date = self.get_time(form_dict["date"])

            award = resume_model.AwardItem(
                title=form_dict["title"],
                date=date,
                issuer=form_dict["issuer"],
                desc=form_dict["desc"],
                url=form_dict["url"]
            )
            self.award_items.append(award)

        elif submit_type == 'save' and form.validate():
            form_dict = _form_to_dict(form)
            creator = Person.objects.get_or_404(email=g.user.email)
            
            resume = context.get('resume')
            form.populate_obj(resume)

            experience = resume_model.Experience(
                _id = ObjectId(),
                items = self.work_items,
                comments = []
            )
            volunteer = resume_model.Volunteer(
                _id = ObjectId(),
                items = self.volunteer_items,
                comments = []
            )
            education = resume_model.Education(
                _id = ObjectId(),
                items = self.education_items,
                comments = []
            )
            awards = resume_model.Awards(
                _id = ObjectId(),
                items = self.award_items,
                comments = []
            )

            pubs = resume_model.Publications(
                _id = ObjectId(),
                items = form_dict['pubs'].split(", "),
                comments = []
            )
            interests = resume_model.Interests(
                _id = ObjectId(),
                items = form_dict['interests'].split(", "),
                comments = []
            )
            languages = resume_model.Languages(
                _id = ObjectId(),
                items = form_dict['languages'].split(", "),
                comments = []
            )
            skills = resume_model.Skills(
                _id = ObjectId(),
                items = form_dict['skills'].split(", "),
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
            self.reset()

            return redirect(url_for('resume_app.list'))
        return redirect(url_for('resume_app.create'))

    def dispatch_request(self, slug):
        if request.method.lower() == 'get':
            return self.get(slug)
        elif request.method.lower() == 'post':
            return self.post(slug)
        return "Improper method used: {}".format(request.method)

def setup_self(resume_app):
    resume_app.add_url_rule('/', view_func=ListView.as_view('list'), 
        methods=['GET', 'POST'])
    resume_app.add_url_rule('/<slug>', view_func=DetailView.as_view('detail'), 
        methods=['GET', 'POST'])

    #defaults added otherwise create crashes as get takes two params
    resume_app.add_url_rule('/create', defaults={'slug': None},
        view_func=CreateView.as_view('create'), methods=['GET', 'POST'])
    resume_app.add_url_rule('/<slug>/edit', view_func=CreateView.as_view('edit'), 
        methods=['GET', 'POST'])