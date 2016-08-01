"""
resume.py: Creates the model for Resume, serving as the
backbone for the system. Implemented in MongoDB

__author__ = "Yash Patel"
__copyright__ = "Copyright 2016, Plytos Inc."

__license__ = "Free/Open"
__version__ = "1.0.0"
__maintainer__ = "Yash Patel"
__email__ = "ypatel@princeton.edu"
"""

from plytos import db
from plytos.models.comments import CommentsPerSection, ToDosPerSection, Comment

class VolunteerItem(db.EmbeddedDocument):
    _id          = db.ObjectIdField()

    org           = db.StringField()
    title         = db.StringField()
    startDt       = db.StringField()
    endDt         = db.StringField()
    url           = db.StringField()
    impact        = db.StringField()

    highlights    = db.ListField(db.StringField())

    def push_highlight(self, text):
        self.highlights.append(text)

    def __str__(self):
        return """
            org: {}
            title: {}
            startDt: {}
            endDt: {}
            url: {}
            impact: {}
            highlights: {}
        """.format(self.org, self.title, self.startDt, 
            self.endDt, self.url, self.impact, self.highlights)

class WorkItem(db.EmbeddedDocument):
    _id           = db.ObjectIdField()

    company       = db.StringField()
    startDt       = db.DateTimeField()
    endDt         = db.DateTimeField()
    position      = db.StringField()
    url           = db.StringField()
    impact        = db.StringField()

    highlights    = db.ListField(db.StringField())
    skills        = db.ListField(db.StringField())

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

    def __str__(self):
        return """
                company: {}
                startDt: {}
                endDt: {}
                position: {}
                url: {}
                impact: {}
                highlights: {}
                skills: {}
            """.format(self.company, self.startDt, self.endDt, 
                self.position, self.url, self.impact, 
                self.highlights, self.skills)

class EducationItem(db.EmbeddedDocument):
    _id          = db.ObjectIdField()

    school       = db.StringField()
    degree       = db.StringField()
    major        = db.StringField()
    startDt      = db.DateTimeField()
    gradDt       = db.DateTimeField()
    gpa          = db.FloatField()
    courses      = db.ListField(db.StringField())

    def push_course(self, course):
        self.courses.append(course)

    def __str__(self):
        return """
                school: {}
                degree: {}
                major: {}
                startDt: {}
                gradDt: {}
                gpa: {}
                courses: {}
            """.format(self.school, self.degree, self.major, 
                self.startDt, self.gradDt, self.gpa, self.courses)

class AwardItem(db.EmbeddedDocument):
    _id          = db.ObjectIdField()

    title        = db.StringField()
    date         = db.DateTimeField()
    issuer       = db.StringField()
    desc         = db.StringField()
    url          = db.StringField()

    def __str__(self):
        return """
                title: {}
                date: {}
                issuer: {}
                desc: {}
                url: {}
            """.format(self.title, self.date, self.issuer, 
                self.desc, self.url)

class Experience(db.EmbeddedDocument):
    _id          = db.ObjectIdField()

    items       = db.ListField(db.EmbeddedDocumentField('WorkItem'))
    comments    = db.ListField(db.EmbeddedDocumentField('Comment'))

    def __str__(self):
        return """
                items: {}
                comments: {}
            """.format(self.items, self.comments)

class Volunteer(db.EmbeddedDocument):
    _id          = db.ObjectIdField()

    items       = db.ListField(db.EmbeddedDocumentField('VolunteerItem'))
    comments    = db.ListField(db.EmbeddedDocumentField('Comment'))

    def __str__(self):
        return """
                items: {}
                comments: {}
            """.format(self.items, self.comments)

class Education(db.EmbeddedDocument):
    _id          = db.ObjectIdField()

    items       = db.ListField(db.EmbeddedDocumentField('EducationItem'))
    comments    = db.ListField(db.EmbeddedDocumentField('Comment'))

    def __str__(self):
        return """
                items: {}
                comments: {}
            """.format(self.items, self.comments)

class Awards(db.EmbeddedDocument):
    _id          = db.ObjectIdField()

    items       = db.ListField(db.EmbeddedDocumentField('AwardItem'))
    comments    = db.ListField(db.EmbeddedDocumentField('Comment'))

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
    awards        = db.EmbeddedDocumentField(Awards)
    
    skills        = db.EmbeddedDocumentField(Skills)
    pubs          = db.EmbeddedDocumentField(Publications)
    interests     = db.EmbeddedDocumentField(Interests)
    languages     = db.EmbeddedDocumentField(Languages)

    comments_per_section = db.EmbeddedDocumentField(CommentsPerSection)
    todos_per_section    = db.EmbeddedDocumentField(ToDosPerSection)

    comments      = db.ListField(db.EmbeddedDocumentField('Comment'))

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