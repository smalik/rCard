from datetime import datetime
from copy import deepcopy
from bson.objectid import ObjectId
from collections import OrderedDict

from app import db
from comments import CommentsPerSection, ToDosPerSection, Comment

class SocialMediaID:
    def __init__(self, network=None, uname=None, url=None):
        self.network    = network
        self.uname      = uname
        self.url        = url
        return None

    def getSocial(self):
        # social = {self.network : {self.uname : self.url}}
        social = [self.network, self.uname, self.url]
        return social

class VolunteerDetail:
    def __init__(self):
        self.org        = None
        self.title      = None
        self.startDt    = None
        self.endDt      = None
        self.url        = None
        self.impact     = None
        self.highlights = []

    def push_highlight(self, text):
        self.highlights.append(text)

class WorkDetail:
    def __init__(self):
        self.company    = None
        self.startDt    = None
        self.endDt      = None
        self.position   = None
        self.url        = None
        self.impact     = None
        self.highlights = []
        self.skills     = []
        return None

    def set_company(self, name):
        self.company = name

    def set_position(self, position):
        self.position = position

    def set_dates(self, start, end):
        self.startDate  = start
        self.endDate    = end
        tenure          = self.endDate - self.startDate

    def set_url(self, url):
        self.url = url

    def set_impact(self, text):
        self.impact = text

    def push_highlight(self, text):
        self.highlights.append(text)

    def push_skill(self, tag):
        self.skills.append(tag)

class EduDetail:
    def __init__(self):
        self.school = None
        self.degree = None
        self.major  = None
        self.startDt= None
        self.gradDt = None
        self.gpa    = None
        self.courses= []

    def push_course(self, course):
        self.courses.append(course)

class AwardItems:
    def __init__(self):
        self.title  = None
        self.date   = None
        self.issuer = None
        self.desc   = None
        self.url    = None
        return None

class Location(db.EmbeddedDocument):
    _id          = db.ObjectIdField()    
    address1    = db.StringField()
    address2    = db.StringField()
    zipcode     = db.StringField()
    city        = db.StringField()
    country     = db.StringField()
    region      = db.StringField()

    comments    = db.ListField(db.IntField())

    def __str__(self):
        return """
            items: {}
            comments: {}
            """.format(self.items, self.comments)

    def __str__(self):
        return """
                address1: {}
                address2: {}
                zipcode: {}
                city: {}
                country: {}
                region: {}
                comments: {}
            """.format(address1, address2, zipcode, city, 
                country, region, comments)

class SocialProfile(db.EmbeddedDocument):
    _id          = db.ObjectIdField()
    items       = db.ListField(db.ListField(db.IntField()))
    comments    = db.ListField(db.IntField())

    def __str__(self):
        return """
                items: {}
                comments: {}
            """.format(self.items, self.comments)

class Experience(db.EmbeddedDocument):
    _id          = db.ObjectIdField()
    items       = db.ListField(db.StringField())
    comments    = db.ListField(db.IntField())

    def __str__(self):
        return """
                items: {}
                comments: {}
            """.format(self.items, self.comments)

class Volunteer(db.EmbeddedDocument):
    _id          = db.ObjectIdField()
    items       = db.ListField(db.StringField())
    comments    = db.ListField(db.IntField())

    def __str__(self):
        return """
                items: {}
                comments: {}
            """.format(self.items, self.comments)

class Education(db.EmbeddedDocument):
    _id          = db.ObjectIdField()
    items       = db.ListField(db.StringField())
    comments    = db.ListField(db.IntField())

    def __str__(self):
        return """
                items: {}
                comments: {}
            """.format(self.items, self.comments)

class Awards(db.EmbeddedDocument):
    _id          = db.ObjectIdField()
    items       = db.ListField(db.StringField())
    comments    = db.ListField(db.IntField())

    def __str__(self):
        return """
                items: {}
                comments: {}
            """.format(self.items, self.comments)

class Publications(db.EmbeddedDocument):
    _id          = db.ObjectIdField()
    items       = db.ListField(db.StringField())
    comments    = db.ListField(db.IntField())

    def __str__(self):
        return """
                items: {}
                comments: {}
            """.format(self.items, self.comments)

class Interests(db.EmbeddedDocument):
    _id          = db.ObjectIdField()
    items       = db.ListField(db.StringField())
    comments    = db.ListField(db.IntField())

    def __str__(self):
        return """
                items: {}
                comments: {}
            """.format(self.items, self.comments)

class Languages(db.EmbeddedDocument):
    _id          = db.ObjectIdField()

    items       = db.ListField(db.StringField())
    comments    = db.ListField(db.IntField())

    def __str__(self):
        return """
                items: {}
                comments: {}
            """.format(self.items, self.comments)

class Skills(db.EmbeddedDocument):
    _id          = db.ObjectIdField()    
    
    # parent      = db.ReferenceField('Person')
    # exp         = db.EmbeddedDocumentField(Experience)
    items       = db.ListField(db.StringField())
    comments    = db.ListField(db.IntField())

    def __str__(self):
        return """
                items: {}
                comments: {}
            """.format(self.items, self.comments)

    def getAllSkills(self, expid , exp):
        return None

class Resume(db.Document):
    # _id          = db.ObjectIdField()    
    parent_user       = db.StringField()

    # info        = db.ReferenceField(Personal)
    experience    = db.EmbeddedDocumentField(Experience)
    volunteer     = db.EmbeddedDocumentField(Volunteer)
    education     = db.EmbeddedDocumentField(Education)

    skills        = db.EmbeddedDocumentField(Skills)
    awards        = db.EmbeddedDocumentField(Awards)
    pubs          = db.EmbeddedDocumentField(Publications)
    interests     = db.EmbeddedDocumentField(Interests)
    languages     = db.EmbeddedDocumentField(Languages)

    comments_per_section = db.EmbeddedDocumentField(CommentsPerSection)
    todos_per_section    = db.EmbeddedDocumentField(ToDosPerSection)

    comments      = db.ListField(db.ReferenceField(Comment))

    # which edit the current resume is -- only applicable for "edit" docs
    # None if referring to original
    version     = db.IntField()
    
    # number of edits that resume has -- only applicable for original
    # None if referring to a derived doc (i.e. an edit)
    num_edits    = db.IntField()
    editDt      = db.ListField(db.DateTimeField())

    slug        = db.StringField()

    def __str__(self):
        return """
            experience: {}
            volunteer: {}
            education: {}
            skills: {}
            awards: {}
            pubs: {}
            interests: {}
            languages: {}
            comments_per_section: {}
            todos_per_section: {}
            version: {}
            num_edits: {}
            editDt: {}
            slug: {}
        """.format(self.experience, self.volunteer, self.education, 
            self.skills, self.awards, self.pubs, self.interests, 
            self.languages, self.comments_per_section, 
            self.todos_per_section, self.version, self.num_edits, 
            self.editDt, self.slug)

class Personal(db.EmbeddedDocument):
    _id          = db.ObjectIdField()    
    parent      = db.ReferenceField('Person')

    location    = db.EmbeddedDocumentField(Location)
    profiles    = db.EmbeddedDocumentField(SocialProfile)

    firstName   = db.StringField()
    lastName    = db.StringField()
    middleName  = db.StringField()
    headline    = db.StringField()
    picture     = db.StringField()
    phone       = db.StringField()
    url         = db.StringField()
    summary     = db.StringField()

    comments    = db.ListField(db.IntField())

    def __str__(self):
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
    _id           = db.ObjectIdField()    
    active        = db.BooleanField()
    email         = db.StringField(required=True) 
    username      = db.StringField(required=True) 
    password_hash = db.BinaryField(required=True)

    # Identity of the person from Personal card
    info          = db.StringField(required=True) # db.EmbeddedDocumentField(Personal)

    # Current finalized resume being used
    final_resumes      = db.ListField(db.ReferenceField(Resume))

    # Most recent save of the resume (not published though)
    working_resumes    = db.ListField(db.ReferenceField(Resume))

    # Set of resumes that are being tracked for edits (when user forks)
    current_edits     = db.ListField(db.ReferenceField(Resume))

    # Resumes the user is editing
    editing_resumes   = db.ListField(db.ReferenceField(Resume))

    # Most recent working resume
    comments      = db.ListField(db.IntField())
    skills        = db.EmbeddedDocumentField('Skills')

    # Get total number of skills
    def getSkillsCount(self):
        return None

    # Let list of all skills
    def generateSkillsList(self):
        return None

    def __str__(self):
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

    def resume_fork(self, resume):
        resume.num_edits += 1
        resume.save()

        self.del_existing(self.editing_resumes, resume.slug)
        edit_version = Resume()

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
        self.del_existing(self.editing_resumes, resume.slug)
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
            'experience': Experience,
            'volunteer': Volunteer,
            'education': Education,
            'skills': Skills,
            'awards': Awards,
            'pubs': Publications,
            'interests': Interests,
            'languages': Languages,
        }

        working_index = self.which_contain_doc(self.working_resumes, slug)
        db_obj = field_class_lookup[field]()

        db_obj._id = ObjectId()
        db_obj.items = edit_value.split(',')
        db_obj.comments = []

        self.working_resumes[working_index][field] = db_obj
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