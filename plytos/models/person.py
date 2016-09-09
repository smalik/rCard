"""
person.py: Creates the model for the user, connected
to the resume model. Implemented in MongoDB

__author__ = "Yash Patel"
__copyright__ = "Copyright 2016, Plytos Inc."

__license__ = "Free/Open"
__version__ = "1.0.0"
__maintainer__ = "Yash Patel"
__email__ = "ypatel@princeton.edu"
"""

from bson.objectid import ObjectId
from collections import OrderedDict
from copy import deepcopy

from plytos import db
from plytos.models.comments import Comment, CommentsPerSection
from plytos.models.personal import Personal
import plytos.models.resume as resume_model

class Person(db.Document):
    """
    Person Data model behaves as follows:
        1.  Whether or not the given user is active
        2.  Account email address (required)
        3.  Account username (required)
        4.  Account password (hashed w/ MD5) (required)
        5.  Identity of the person from Personal card (required)
        6.  Current finalized resume being used
        7.  Most recent save of the resume (not published though)
        8.  Set of resumes that are being tracked for edits
        9.  Resumes the user is editing
        10. List of comments associated to overall user
        11. Skills associated with overal user account
    """

    meta = {'collection': 'users'}

    _id           = db.ObjectIdField(required=True)    
    active        = db.BooleanField()
    email         = db.StringField(required=True) 
    username      = db.StringField(required=True) 
    password_hash = db.BinaryField()

    info          = db.StringField()
    personal      = db.EmbeddedDocumentField('Personal')

    comments          = db.ListField(db.ObjectIdField())
    requests          = db.ListField(db.ObjectIdField())
    friends           = db.ListField(db.ObjectIdField())

    # list of all resumes that have been published
    final_resumes     = db.ListField(db.ObjectIdField())

    # list of resumes that are currently in the works
    working_resumes   = db.ListField(db.ObjectIdField())

    # list of resumes that have been submitted back (pending review)
    current_edits     = db.ListField(db.ObjectIdField())

    # list of resumes that are being edited
    editing_resumes   = db.ListField(db.ObjectIdField())

    # gamification attributes (used for exchange/monetization)
    coins         = db.IntField()
    points        = db.IntField()

    # Get total number of skills
    def getSkillsCount(self):
        return len(skills)

    # Let list of all skills
    def generateSkillsList(self):
        return skills

    def reset_password(self, password):
        self.password_hash = password

        self.switch_db("users")
        self.save()

    def is_active(self):
        return self.active

    def get_id(self):
        return self._id

    def is_authenticated(self):
        return True

    def is_anonymous(self):
        return False

    def __str__(self):
        """ Returns a formatting string for printing a user """
        return """
                personal: {}
                active: {}
                email: {}
                username: {}
                password_hash: {}
                info: {}
                final_resume: {}
                working_resume: {}
                current_edits: {}
                editing_resumes: {}
                comments: {}
            """.format(self.personal, self.active, self.email,  self.username, 
                self.password_hash, self.info, self.final_resumes, 
                self.working_resumes, self.current_edits, self.editing_resumes, 
                self.comments)

    ################## Editor Version Control Funcs #########################
    def resume_fork(self, resume):
        from plytos.views.get import resume_with_id
        forms = ['work', 'volunteer', 'education', 'awards', 'skills', 
            'publications', 'interests', 'languages']

        for edit_id in self.editing_resumes:
            if resume_with_id(edit_id).parent_resume == resume._id:
                return

        # makes an editing copy of the resume and saves it
        edit_version = resume_model.Resume()
        for field in resume:
            edit_version[field] = resume[field]
            try:
                edit_version[field].comments = []
            except: pass

        comments_per_section = CommentsPerSection()
        for form in forms:
            comments_per_section[form] = 0
        comments_per_section._id    = ObjectId()
        edit_version.comments_per_section = comments_per_section

        edit_version._id = ObjectId()
        edit_version.parent_resume = resume._id
        edit_version.switch_db("resumes")
        edit_version.save()

        # adds this editing copy to the list of resumes 
        # being edited by the user at hand
        self.editing_resumes.append(edit_version._id)

        self.switch_db("users")
        self.save()

    def resume_submit(self, resume):
        from plytos.views.get import person_with_id, resume_with_id
        forms = ['work', 'volunteer', 'education', 'awards', 'skills', 
            'publications', 'interests', 'languages']

        # updates the analytics on comments
        working_resume = resume_with_id(resume.parent_resume)
        for form in forms:
            working_resume.comments_per_section[form] += \
                len(resume[form].comments)
        working_resume.switch_db("resumes")
        working_resume.save()

        parent = person_with_id(resume.parent_user)
        parent.current_edits.append(resume._id)
        parent.switch_db("users")
        parent.save()

        self.editing_resumes.remove(resume._id)
        self.switch_db("users")
        self.save()

    ################## Owner Version Control Funcs #############################
    def get_sorted_edits(self):
        from plytos.views.get import resume_with_id
        sorted_edits = OrderedDict()
        for resume in self.current_edits:
            parent_id =  resume_with_id(resume).parent_resume
            if parent_id not in sorted_edits:
                sorted_edits[parent_id] = []
            sorted_edits[parent_id].append(str(resume))
        return sorted_edits

    def overall_accept(self, _id, form_type, which_orig_form, 
        which_edit_form, is_new):

        from plytos.views.get import resume_with_id
        obj_lookup = {
            'work'          : resume_model.WorkItem,
            'volunteer'     : resume_model.VolunteerItem,
            'education'     : resume_model.EducationItem,
            'awards'        : resume_model.AwardItem,
            'skills'        : resume_model.SkillItem,
            'publications'  : resume_model.PublicationItem,
            'interests'     : resume_model.InterestItem,
            'languages'     : resume_model.LanguageItem,
        }

        current_edit   = resume_with_id(_id)
        working_resume = resume_with_id(current_edit.parent_resume)

        # case where the original form was directly edited -- no deletes
        if which_orig_form is not None and which_edit_form is not None:
            transfer_form  = current_edit[form_type].items[which_edit_form]
            for field in transfer_form:
                working_resume[form_type].items[which_orig_form][field] \
                    = transfer_form[field]

        # case where a new item was added
        elif which_orig_form is None:
            new_obj     = obj_lookup[form_type]()
            new_obj._id        = ObjectId()
            new_obj.parent_id  = ObjectId(_id)
            new_obj.edit_ids   = []

            transfer_form  = current_edit[form_type].items[which_edit_form]
            for field in transfer_form:
                new_obj[field] = transfer_form[field]
            working_resume[form_type].items.append(new_obj)

        # case where an original item was deleted was added
        elif which_edit_form is None:
            delete_value = working_resume[form_type].items[which_orig_form]
            working_resume[form_type].deleted_items.append(delete_value)
            working_resume[form_type].items.pop(which_orig_form)

        if which_edit_form is not None and is_new:
            working_resume[form_type].items[which_edit_form].edit_ids.append(_id)

        working_resume.switch_db("resumes")
        working_resume.save()

    def internal_accept(self, _id, form_type, which_orig_form, 
        which_edit_form, field, is_new):

        from plytos.views.get import resume_with_id
        obj_lookup = {
            'work'          : resume_model.WorkItem,
            'volunteer'     : resume_model.VolunteerItem,
            'education'     : resume_model.EducationItem,
            'awards'        : resume_model.AwardItem,
            'skills'        : resume_model.SkillItem,
            'publications'  : resume_model.PublicationItem,
            'interests'     : resume_model.InterestItem,
            'languages'     : resume_model.LanguageItem,
        }

        current_edit   = resume_with_id(_id)
        working_resume = resume_with_id(current_edit.parent_resume) 

        # case where the original form was directly edited -- no deletes
        if which_orig_form is not None and which_edit_form is not None:
            edit = current_edit[form_type].items[which_edit_form][field]
            working_resume[form_type].items[which_orig_form][field] = edit

        # case where a new item was added
        elif which_orig_form is None:
            new_obj = obj_lookup[form_type]()
            new_obj._id = current_edit[form_type].items[which_edit_form]._id
            new_obj.parent_id  = ObjectId(_id)
            new_obj.edit_ids   = []

            new_obj[field] = current_edit[form_type].items[which_edit_form][field]
            working_resume[form_type].items.append(new_obj)

        # case where an original item was deleted was added
        elif which_edit_form is None:
            working_resume[form_type].items[which_orig_form][field] = None

        if which_edit_form is not None and is_new:
            working_resume[form_type].items[which_edit_form].edit_ids.append(_id)
        working_resume.switch_db("resumes")
        working_resume.save()

    def resume_publish(self, _id):
        # finds the working resume and sees if there is already a finalized
        # version corresponding to it -- deletes if exists
        from plytos.views.personal import new_resume
        from plytos.views.get import resume_with_id

        to_publish = resume_with_id(_id)
        finalized_resume = new_resume(ObjectId(), 
            work=to_publish.work.items, 
            volunteer=to_publish.volunteer.items, 
            education=to_publish.education.items, 
            awards=to_publish.awards.items, 
            publications=to_publish.publications.items, 
            interests=to_publish.interests.items, 
            languages=to_publish.languages.items, 
            skills=to_publish.skills.items)
        finalized_resume.parent_resume = _id
        finalized_resume.switch_db("resumes")
        finalized_resume.save()
        
        self.final_resumes.append(finalized_resume._id)
        self.switch_db("users")
        self.save()