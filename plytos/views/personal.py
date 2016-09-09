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
from plytos.forms import (BasicForm, WorkForm, VolunteerForm, 
    EducationForm, AwardForm, SkillForm, PublicationForm, 
    InterestForm, LanguageForm, CommentForm)

from plytos.models.comments import Comment, CommentsPerSection
from plytos.models.todo import ToDosPerSection
import plytos.models.resume as resume_model
from plytos.models.person import Person
from plytos.models.personal import Personal
from plytos.views.get import (resume_with_id, comments_with_id,
    resume_with_ids, person_with_username)

def new_resume(_id, work=[], volunteer=[], education=[], 
        awards=[], publications=[], interests=[], 
        languages=[], skills=[]):
    
    forms = ['work', 'volunteer', 'education', 'awards', 'skills', 
        'publications', 'interests', 'languages']
    creator = person_with_username(g.user.username)
    resume = resume_model.Resume()
    resume._id = _id

    if creator.personal is not None:
        resume.personal = creator.personal
    else: 
        resume.personal     = Personal()
        resume.personal._id = ObjectId()

    resume.work = resume_model.Work(
        _id = ObjectId(),
        items = work,
        deleted_items = [],
        comments = []
    )
    resume.volunteer = resume_model.Volunteer(
        _id = ObjectId(),
        items = volunteer,
        deleted_items = [],
        comments = []
    )
    resume.education = resume_model.Education(
        _id = ObjectId(),
        items = education,
        deleted_items = [],
        comments = []
    )
    resume.awards = resume_model.Awards(
        _id = ObjectId(),
        items = awards,
        deleted_items = [],
        comments = []
    )
    resume.publications = resume_model.Publications(
        _id = ObjectId(),
        items = publications,
        deleted_items = [],
        comments = []
    )
    resume.interests = resume_model.Interests(
        _id = ObjectId(),
        items = interests,
        deleted_items = [],
        comments = []
    )
    resume.languages = resume_model.Languages(
        _id = ObjectId(),
        items = languages,
        deleted_items = [],
        comments = []
    )
    resume.skills = resume_model.Skills(
        _id = ObjectId(),
        items = skills,
        deleted_items = [],
        comments = []
    )

    resume.parent_resume = None
    resume.parent_user   = creator._id

    resume.comments          = []
    resume.complete_todos    = []
    resume.incomplete_todos  = []

    comments_per_section = CommentsPerSection()
    for form in forms:
        comments_per_section[form] = 0
    comments_per_section._id    = ObjectId()
    resume.comments_per_section = comments_per_section

    resume.switch_db("resumes")
    resume.save()
    return resume

class ListView(View):
    decorators = [login_required]

    def get(self, view):
        # Listview only show particular user's resume
        creator = person_with_username(g.user.username)
        if view == 'review':
            resumes = resume_with_ids(creator.current_edits)
        elif view == 'revise':
            resumes = resume_with_ids(creator.editing_resumes)
        elif view == 'finalized': 
            resumes = resume_with_ids(creator.final_resumes)
        elif view == 'edit' or view == 'history':
            resumes = resume_with_ids(creator.working_resumes)

        return render_template('resumes/list.html', view=view, 
            resumes=resumes)

    def post(self, view):
        dbUser = person_with_username(g.user.username)
        edit_index = int(request.form["location"])
        resume = resume_with_id(dbUser.editing_resumes[edit_index])
        dbUser.resume_submit(resume)
        return redirect(url_for('resume_app.list', view=view))

    def dispatch_request(self, view):
        if request.method.lower() == 'get':
            return self.get(view)
        if request.method.lower() == 'post':
            return self.post(view)
        return "Improper method used: {}".format(request.method)

class CreateView(View):
    decorators = []#login_required]
    CHOICES = ((1, "experience"), (2, "education"), 
        (3, "activities"), (4, "honors"), (5, "publication"))

    fields = ["work_items", "volunteer_items", 
        "education_items", "award_items", "skill_items", 
        "publication_items", "interest_items", "language_items"]

    resume_id           = ObjectId()

    def get_context(self):
        try: 
            resume = resume_with_id(self.resume_id)
        except:
            resume = new_resume(_id=self.resume_id)

        work_forms = [WorkForm(obj=work) 
            for work in resume.work.items]
        volunteer_forms = [VolunteerForm(obj=volunteer) 
            for volunteer in resume.volunteer.items]
        education_forms = [EducationForm(obj=education) 
            for education in resume.education.items]
        award_forms = [AwardForm(obj=award) 
            for award in resume.awards.items]

        skill_forms = [SkillForm(obj=skill) 
            for skill in resume.skills.items]
        publication_forms = [PublicationForm(obj=publication) 
            for publication in resume.publications.items]
        interest_forms = [InterestForm(obj=interest) 
            for interest in resume.interests.items]
        language_forms = [LanguageForm(obj=language) 
            for language in resume.languages.items]

        work_comment_forms = [CommentForm(obj=comments_with_id(
            comment, "work")) for comment in resume.work.comments]
        volunteer_comment_forms = [CommentForm(obj=comments_with_id(
            comment, "volunteer")) for comment in resume.volunteer.comments]
        education_comment_forms = [CommentForm(obj=comments_with_id(
            comment, "education")) for comment in resume.education.comments]
        award_comment_forms = [CommentForm(obj=comments_with_id(
            comment, "awards")) for comment in resume.awards.comments]
        skill_comment_forms = [CommentForm(obj=comments_with_id(
            comment, "skills")) for comment in resume.skills.comments]
        publication_comment_forms = [CommentForm(obj=comments_with_id(
            comment, "publications")) for comment in resume.publications.comments]
        interest_comment_forms = [CommentForm(obj=comments_with_id(
            comment, "interests")) for comment in resume.interests.comments]
        language_comment_forms = [CommentForm(obj=comments_with_id(
            comment, "languages")) for comment in resume.languages.comments]

        context = {
            "basic_form": BasicForm(obj=resume.personal),
            "work_form": WorkForm(),
            "volunteer_form": VolunteerForm(),
            "education_form": EducationForm(),
            "award_form": AwardForm(),

            "skill_form": SkillForm(),
            "publication_form": PublicationForm(),
            "interest_form": InterestForm(),
            "language_form": LanguageForm(),

            "work_forms": work_forms,
            "volunteer_forms": volunteer_forms,
            "education_forms": education_forms,
            "award_forms": award_forms,
            "skill_forms": skill_forms,
            "publication_forms": publication_forms,
            "interest_forms": interest_forms,
            "language_forms": language_forms,

            "work_comment_forms": work_comment_forms,
            "volunteer_comment_forms": volunteer_comment_forms,
            "education_comment_forms": education_comment_forms,
            "award_comment_forms": award_comment_forms,
            "skill_comment_forms": skill_comment_forms,
            "publication_comment_forms": publication_comment_forms,
            "interest_comment_forms": interest_comment_forms,
            "language_comment_forms": language_comment_forms,

            "comment_form": CommentForm()
        }

        return context

    def get(self, edit):
        if edit is None: edit = 'edit'
        context = self.get_context()
        return render_template('resumes/create.html', **context,
            view=edit)

    def _create_from_form(self, form, obj, edit_history=[]):
        instance            = obj()
        form.populate_obj(instance)
        instance._id        = ObjectId()
        instance.parent_id  = ObjectId(self.resume_id)
        instance.edit_ids   = edit_history
        return instance

    def post(self, _id, edit):
        if edit is None:
            edit = 'edit'
        context = self.get_context()
        creator = person_with_username(g.user.username)
        resume  = resume_with_id(self.resume_id)

        submit_type = request.form['submit'].split()[-1].strip().lower()
        
        basic_form = context.get("basic_form")
        work_form = context.get("work_form")
        volunteer_form = context.get("volunteer_form")
        education_form = context.get("education_form")
        award_form = context.get("award_form")

        skill_form = context.get("skill_form")
        publication_form = context.get("publication_form")
        interest_form = context.get("interest_form")
        language_form = context.get("language_form")

        work_forms = context.get('work_forms')
        volunteer_forms = context.get('volunteer_forms')
        education_forms = context.get('education_forms')
        award_forms = context.get('award_forms')
        skill_forms = context.get('skill_forms')
        publication_forms = context.get('publication_forms')
        interest_forms = context.get('interest_forms')
        language_forms = context.get('language_forms')

        work_comment_forms = context.get('work_comment_forms')
        volunteer_comment_forms = context.get('volunteer_comment_forms')
        education_comment_forms = context.get('education_comment_forms')
        award_comment_forms = context.get('award_comment_forms')
        skill_comment_forms = context.get('skill_comment_forms')
        publication_comment_forms = context.get('publication_comment_forms')
        interest_comment_forms = context.get('interest_comment_forms')
        language_comment_forms = context.get('language_comment_forms')

        comment_form   = context.get('comment_form')

        if submit_type == "delete":
            values = request.form["location"].split("_")
            edit_field = values[0]
            edit_index = int(values[1])

            delete_value = resume[edit_field].items[edit_index]
            resume[edit_field].deleted_items.append(delete_value)
            resume[edit_field].items.pop(edit_index)

        elif submit_type == "edit":
            values = request.form["location"].split("_")
            edit_field = values[0]
            edit_index = int(values[1])

            if edit_field == 'work' and \
                work_forms[edit_index].validate():
                
                work = self._create_from_form(work_forms[edit_index], 
                    resume_model.WorkItem, resume.work.items[edit_index].edit_ids)
                work._id = resume.work.items[edit_index]._id
                work.highlights = work.highlights.split(",")
                resume.work.items[edit_index] = work

            elif edit_field == 'volunteer' and \
                volunteer_forms[edit_index].validate():
                
                volunteer            = self._create_from_form(
                    volunteer_forms[edit_index], resume_model.VolunteerItem,
                    resume.volunteer.items[edit_index].edit_ids)
                volunteer.highlights = volunteer.highlights.split(",")
                volunteer._id = resume.volunteer.items[edit_index]._id
                resume.volunteer.items[edit_index] = volunteer

            elif edit_field == 'education' and \
                education_forms[edit_index].validate():
                
                education            = self._create_from_form(
                    education_forms[edit_index], resume_model.EducationItem,
                    resume.education.items[edit_index].edit_ids)
                education.courses    = education.courses.split(",")
                education._id = resume.education.items[edit_index]._id
                resume.education.items[edit_index] = education

            elif edit_field == 'awards' and \
                award_forms[edit_index].validate():
                
                award            = self._create_from_form(
                    award_forms[edit_index], resume_model.AwardItem,
                    resume.awards.items[edit_index].edit_ids)
                award._id = resume.awards.items[edit_index]._id
                resume.awards.items[edit_index] = award

            elif edit_field == 'skills' and \
                skill_forms[edit_index].validate():
                
                skill            = self._create_from_form(
                    skill_forms[edit_index], resume_model.SkillItem,
                    resume.skills.items[edit_index].edit_ids)
                skill._id = resume.skills.items[edit_index]._id
                resume.skills.items[edit_index] = skill

            elif edit_field == 'publications' and \
                publication_forms[edit_index].validate():
                
                publication            = self._create_from_form(
                    publication_forms[edit_index], resume_model.PublicationItem,
                    resume.publications.items[edit_index].edit_ids)
                publication._id = resume.publications.items[edit_index]._id
                resume.publications.items[edit_index] = publication

            elif edit_field == 'interests' and \
                interest_forms[edit_index].validate():
                
                interest            = self._create_from_form(
                    interest_forms[edit_index], resume_model.InterestItem,
                    resume.interests.items[edit_index].edit_ids)
                interest._id = resume.interests.items[edit_index]._id
                resume.interests.items[edit_index] = interest

            elif edit_field == 'languages' and \
                language_forms[edit_index].validate():
                
                language            = self._create_from_form(
                    language_forms[edit_index], resume_model.LanguageItem,
                    resume.languages.items[edit_index].edit_ids)
                language._id = resume.languages.items[edit_index]._id
                resume.languages.items[edit_index] = language

            elif basic_form.validate():
                resume.personal = self._create_from_form(basic_form, 
                    resume_model.Personal)

        elif submit_type == "comment":
            values = request.form["location"].split("_")
            edit_field = values[0]

            if comment_form.validate():
                comment          = Comment()
                comment_form.populate_obj(comment)

                comment._id      = ObjectId()
                comment.upvote   = 0
                comment.downvote = 0
                comment.author_user = creator._id

            if len(values) == 1:
                resume[edit_field].comments.append(comment._id)
                resume.comments_per_section[edit_field] += 1
            else: 
                comment._id = \
                    resume[edit_field].comments[int(values[1])]

            comment.switch_db("{}_comments".format(edit_field))
            comment.save()

        elif submit_type == "create":
            create_field = request.form["location"]

            if create_field == 'work' and work_form.validate():
                work            = self._create_from_form(work_form, 
                    resume_model.WorkItem)
                work.highlights = work.highlights.split(",")
                resume.work.items.append(work)

            elif create_field == 'volunteer' and volunteer_form.validate():
                volunteer            = self._create_from_form(volunteer_form, 
                    resume_model.VolunteerItem)
                volunteer.highlights = volunteer.highlights.split(",")
                resume.volunteer.items.append(volunteer)

            elif create_field == 'education' and education_form.validate():
                education            = self._create_from_form(education_form, 
                    resume_model.EducationItem)
                education.courses    = education.courses.split(",")
                resume.education.items.append(education)

            elif create_field == 'awards' and award_form.validate():
                award            = self._create_from_form(award_form, 
                    resume_model.AwardItem)
                resume.awards.items.append(award)

            elif create_field == 'skills' and skill_form.validate():
                skill            = self._create_from_form(skill_form, 
                    resume_model.SkillItem)
                resume.skills.items.append(skill)

            elif create_field == 'publications' and publication_form.validate():
                publication            = self._create_from_form(publication_form, 
                    resume_model.PublicationItem)
                resume.publications.items.append(publication)

            elif create_field == 'interests' and interest_form.validate():
                interest            = self._create_from_form(interest_form, 
                    resume_model.InterestItem)
                resume.interests.items.append(interest)

            elif create_field == 'languages' and language_form.validate():
                language            = self._create_from_form(language_form, 
                    resume_model.LanguageItem)
                resume.languages.items.append(language)

            else:
                resume.personal = self._create_from_form(basic_form, 
                    resume_model.Personal)

                if edit == 'edit':
                    copy_resume = new_resume(ObjectId(), 
                        work=resume.work.items, 
                        volunteer=resume.volunteer.items, 
                        education=resume.education.items, 
                        awards=resume.awards.items, 
                        publications=resume.publications.items, 
                        interests=resume.interests.items, 
                        languages=resume.languages.items, 
                        skills=resume.skills.items)
                    copy_resume.parent_resume = self.resume_id
                    copy_resume.switch_db("resumes")
                    copy_resume.save()

                    fields = ['work', 'volunteer', 'education', 'languages',
                        'awards', 'skills', 'publications', 'interests']
                    for field in fields:
                        for item in resume[field].items:
                            item.edit_ids.append(copy_resume._id)
                        
                resume.switch_db("resumes")
                resume.save()
                if _id is None:
                    creator.working_resumes.append(self.resume_id)
                    creator.switch_db("users")
                    creator.save()
                return redirect(url_for('resume_app.list', view=edit))
                
        resume.switch_db("resumes")
        resume.save()
        
        if _id is not None:
            if edit is not None:
                return redirect(url_for('resume_app.revise', slug=str(_id),
                    edit=edit))
            return redirect(url_for('resume_app.revise', slug=str(_id)))
        return redirect(url_for('resume_app.create'))

    def dispatch_request(self, edit=None, slug=None):
        _id = None
        if slug is not None:
            _id            = ObjectId(slug)
            self.resume_id = _id

        if request.method.lower() == 'get':
            return self.get(edit)
        elif request.method.lower() == 'post':
            return self.post(_id, edit)
        return "Improper method used: {}".format(request.method)

def setup_self(resume_app):
    resume_app.add_url_rule('/<view>', 
        view_func=ListView.as_view('list'), methods=['GET', 'POST'])
    resume_app.add_url_rule('/create', 
        view_func=CreateView.as_view('create'), methods=['GET', 'POST'])
    resume_app.add_url_rule('/<edit>/<slug>', 
        view_func=CreateView.as_view('revise'), methods=['GET', 'POST'])