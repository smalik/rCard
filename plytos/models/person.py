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

from plytos import db
from plytos.models.comments import Comment
import plytos.models.resume as resume_model

class Location(db.EmbeddedDocument):
    """
    ToDosPerSection Data model behaves as follows:
        1.  First line of the address (required)
        2.  Second line of address
        3.  Zip code of location
        4.  City of location
        5.  Country of location
        6.  Region of location
    """

    _id          = db.ObjectIdField(required=True) 

    address1    = db.StringField(required=True)
    address2    = db.StringField()
    zipcode     = db.StringField()
    city        = db.StringField()
    country     = db.StringField()
    region      = db.StringField()

    def __str__(self):
        """ Returns a formatting string for printing locations """
        return """
                address1: {}
                address2: {}
                zipcode: {}
                city: {}
                country: {}
                region: {}
                comments: {}
            """.format(self.address1, self.address2, self.zipcode, 
                self.city, self.country, self.region, self.comments)

class SocialMediaItem(db.EmbeddedDocument):
    """
    SocialMediaItem Data model behaves as follows:
        1.  Name of the social media network (required)
        2.  Username on the network
        3.  URL of personal profile page (required)
    """

    _id          = db.ObjectIdField(required=True)

    network       = db.StringField(required=True)
    uname         = db.StringField()
    url           = db.StringField()

    def __str__(self):
        """ Returns a formatting string for printing social media """
        return """
                network: {}
                uname: {}
                url: {}
            """.format(self.network, self.uname, self.url)

class SocialProfile(db.EmbeddedDocument):
    """
    SocialProfile Data model behaves as follows:
        1.  List of all social media pages (required)
        2.  List of comments associated to profile
    """

    _id          = db.ObjectIdField(required=True)

    items       = db.ListField(db.EmbeddedDocumentField('SocialMediaItem'),
        required=True)
    comments    = db.ListField(db.IntField())

    def __str__(self):
        """ Returns a formatting string for printing profiles """
        return """
                items: {}
                comments: {}
            """.format(self.items, self.comments)

class Personal(db.EmbeddedDocument):
    """
    Personal Data model behaves as follows:
        1.  Username to whom the personal info belonds 
        2.  Location associated with the user
        3.  Social profiles of the user
        4.  First name (required)
        5.  Last name
        6.  Middle name
        7.  One-line description of person
        8.  User picture/snapshot
        9.  Phone number
        10. Homepage/URL of the user (i.e. profile)
        11. Text description self (extension of headline)
        12. List of comments associated to personal info
    """

    _id          = db.ObjectIdField(required=True)    
    parent      = db.ReferenceField('Person')

    location    = db.EmbeddedDocumentField(Location)
    profiles    = db.EmbeddedDocumentField(SocialProfile)

    firstName   = db.StringField(required=True)
    lastName    = db.StringField()
    middleName  = db.StringField()
    headline    = db.StringField()
    picture     = db.StringField()
    phone       = db.StringField()
    url         = db.StringField()
    summary     = db.StringField()

    comments    = db.ListField(db.IntField())

    def __str__(self):
        """ Returns a formatting string for printing personal attributes """
        return """
            location: {}
            profiles: {}
            firstName: {}
            lastName: {}
            middleName: {}
            headline: {}
            picture: {}
            phone: {}
            url: {}
            summary: {}
            comments: {}
        """.format(self.location, self.profiles, self.firstName, 
            self.lastName, self.middleName, self.headline, self.picture, 
            self.phone, self.url, self.summary, self.comments)

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
    password_hash = db.BinaryField(required=True)

    info          = db.StringField(required=True) # db.EmbeddedDocumentField(Personal)

    final_resumes      = db.ListField(db.ReferenceField(resume_model.Resume))
    working_resumes    = db.ListField(db.ReferenceField(resume_model.Resume))\
    current_edits     = db.ListField(db.ReferenceField(resume_model.Resume))
    editing_resumes   = db.ListField(db.ReferenceField(resume_model.Resume))

    comments      = db.ListField(db.IntField())
    skills        = db.EmbeddedDocumentField('Skills')

    # Get total number of skills
    def getSkillsCount(self):
        return len(skills)

    # Let list of all skills
    def generateSkillsList(self):
        return skills

    def reset_password(self, password):
        self.password_hash = password
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
                skills: {}
            """.format(self.active, self.email,  self.username, 
                self.password_hash, self.info, self.final_resumes, 
                self.working_resumes, self.current_edits, self.editing_resumes, 
                self.comments, self.skills)

    ################## Editor Version Control Funcs ##########################
    # used to determine (for final_resumes, working_resumes, and
    # editing_resumes) if the resume is contained
    def which_contain_doc(self, which, slug):
        for i in range(len(which)):
            if which[i].slug == slug:
                return i
        return None

    # deletes an instance of an object with "slug" and in the particular
    # array (typically working_resumes etc...) that is specified
    def del_existing(self, which, slug):
        which = [item for item in which if item.slug != slug]
        return which

    def resume_fork(self, resume):
        resume.num_edits += 1
        resume.save()

        self.editing_resumes = self.del_existing(self.editing_resumes, 
            resume.slug)
        edit_version = resume_model.Resume()

        # makes an editing copy of the resume and saves it
        for field in resume:
            if field != 'id':
                edit_version[field] = resume[field]

        edit_version.num_edits = None
        edit_version.version = resume.num_edits
        edit_version.save()
        
        # adds this editing copy to the list of resumes 
        # being edited by the user at hand
        self.editing_resumes.append(edit_version)
        self.save()

    def resume_save(self, resume):
        self.editing_resumes = self.del_existing(self.editing_resumes, 
            resume.slug)
        self.editing_resumes.append(resume)
        self.save()

    def resume_submit(self, resume):
        parent = Person.objects.get_or_404(username=resume.parent_user)
        parent.current_edits.append(resume)
        parent.save()

    ################## Owner Version Control Funcs #############################
    def get_sorted_edits(self):
        sorted_edits = OrderedDict()
        for resume in self.current_edits:
            try:
                if resume.slug not in sorted_edits:
                    sorted_edits[resume.slug] = []
                sorted_edits[resume.slug].append(resume)
            except:
                pass
        return sorted_edits

    def resume_accept(self, slug, field, edit_value):
        field_class_lookup = {
            'skills': resume_model.Skills,
            'pubs': resume_model.Publications,
            'interests': resume_model.Interests,
            'languages': resume_model.Languages,
        }

        working_index = self.which_contain_doc(self.working_resumes, slug)
        db_obj = field_class_lookup[field]()

        db_obj._id = ObjectId()
        db_obj.items = edit_value.split(',')
        db_obj.comments = []

        self.working_resumes[working_index][field] = db_obj
        self.working_resumes[working_index].save()

    def internal_accept(self, slug, form_type, which_form, field, edit):
        field_class_lookup = {
            'experience': resume_model.WorkItem,
            'volunteer': resume_model.VolunteerItem,
            'education': resume_model.EducationItem,
            'awards': resume_model.AwardItem
        } 

        working_index = self.which_contain_doc(self.working_resumes, slug)
        self.working_resumes[working_index][form_type].items[which_form][field] = edit
        self.working_resumes[working_index].save()

    def resume_publish(self, slug):
        # finds the working resume and sees if there is already a finalized
        # version corresponding to it -- deletes if exists
        working_resume = self.which_contain_doc(self.working_resumes, slug)
        
        self.del_existing(self.final_resumes, slug)
        self.final_resumes.append(self.working_resumes[working_resume])

        # removes all edits corresponding to it
        self.current_edits = [edit for edit in 
            self.current_edits if slug != edit.slug]
        self.save()