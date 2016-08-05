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
    """
    VolunteerItem Data model behaves as follows:
        1.  Organization at which user did this volunteer work (required)
        2.  Title/Type of volunteering
        3.  Date volunteering started
        4.  Date volunteering ended
        5.  URL of the volunteer organization/opportunity
        6.  Impact description of experience
        7.  List of highlights from volunteer experience
    """

    _id          = db.ObjectIdField(required=True)

    org           = db.StringField(required=True)
    title         = db.StringField()
    startDt       = db.StringField()
    endDt         = db.StringField()
    url           = db.StringField()
    impact        = db.StringField()

    highlights    = db.ListField(db.StringField())

    def __str__(self):
        """ Returns a formatting string for printing volunteer instances """
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
    """
    WorkItem Data model behaves as follows:
        1.  Organization at which user did this work work (required)
        2.  Title/Type of volunteering
        3.  Date volunteering started
        4.  Date volunteering ended
        5.  URL of the volunteer organization/opportunity
        6.  Impact description of experience
        7.  List of highlights from volunteer experience
        8.  Skills gained as a result of work
    """

    _id           = db.ObjectIdField(required=True)

    company       = db.StringField(required=True)
    position      = db.StringField()
    startDt       = db.DateTimeField()
    endDt         = db.DateTimeField()
    url           = db.StringField()
    impact        = db.StringField()

    highlights    = db.ListField(db.StringField())
    skills        = db.ListField(db.StringField())

    def __str__(self):
        """ Returns a formatting string for printing work instances """
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
    """
    EducationItem Data model behaves as follows:
        1.  School at which studied (required)
        2.  Degree earned
        3.  What major studied (or N/a)
        4.  Date school started
        5.  Date school ended
        6.  Final GPA (or current GPA)
        7.  List of courses attended (highlights)
    """
    
    _id          = db.ObjectIdField(required=True)

    school       = db.StringField(required=True)
    degree       = db.StringField()
    major        = db.StringField()
    startDt      = db.DateTimeField()
    gradDt       = db.DateTimeField()
    gpa          = db.FloatField()
    courses      = db.ListField(db.StringField())

    def push_course(self, course):
        self.courses.append(course)

    def __str__(self):
        """ Returns a formatting string for printing education instances """
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
    """
    EducationItem Data model behaves as follows:
        1.  Title of the award given 
        2.  When the award was handed out
        3.  Who provided the award
        4.  What the significance of the award is
        5.  URL of company/cevent from which award received
    """
    
    _id          = db.ObjectIdField(required=True)

    title        = db.StringField(required=True)
    date         = db.DateTimeField()
    issuer       = db.StringField()
    desc         = db.StringField()
    url          = db.StringField()

    def __str__(self):
        """ Returns a formatting string for printing award instances """
        return """
                title: {}
                date: {}
                issuer: {}
                desc: {}
                url: {}
            """.format(self.title, self.date, self.issuer, 
                self.desc, self.url)

class Experience(db.EmbeddedDocument):
    """
    Experience Data model behaves as follows:
        1.  List of work experiences
        2.  Comments others have about this list of experiences
    """
    
    _id          = db.ObjectIdField(required=True)

    items       = db.ListField(db.EmbeddedDocumentField('WorkItem'))
    comments    = db.ListField(db.EmbeddedDocumentField('Comment'))

    def __str__(self):
        """ Returns a formatting string for printing experience lists """
        return """
                items: {}
                comments: {}
            """.format(self.items, self.comments)

class Volunteer(db.EmbeddedDocument):
    """
    Volunteer Data model behaves as follows:
        1.  List of volunteer experiences
        2.  Comments others have about this list of experiences
    """

    _id          = db.ObjectIdField(required=True)

    items       = db.ListField(db.EmbeddedDocumentField('VolunteerItem'))
    comments    = db.ListField(db.EmbeddedDocumentField('Comment'))

    def __str__(self):
        """ Returns a formatting string for printing volunteer lists """
        return """
                items: {}
                comments: {}
            """.format(self.items, self.comments)

class Education(db.EmbeddedDocument):
    """
    Education Data model behaves as follows:
        1.  List of school experiences
        2.  Comments others have about this list of experiences
    """

    _id          = db.ObjectIdField(required=True)

    items       = db.ListField(db.EmbeddedDocumentField('EducationItem'))
    comments    = db.ListField(db.EmbeddedDocumentField('Comment'))

    def __str__(self):
        """ Returns a formatting string for printing education lists """
        return """
                items: {}
                comments: {}
            """.format(self.items, self.comments)

class Awards(db.EmbeddedDocument):
    """
    Awards Data model behaves as follows:
        1.  List of awards
        2.  Comments others have about this list of awards
    """

    _id          = db.ObjectIdField(required=True)

    items       = db.ListField(db.EmbeddedDocumentField('AwardItem'))
    comments    = db.ListField(db.EmbeddedDocumentField('Comment'))

    def __str__(self):
        """ Returns a formatting string for printing awards lists """
        return """
                items: {}
                comments: {}
            """.format(self.items, self.comments)

class Publications(db.EmbeddedDocument):
    """
    Publications Data model behaves as follows:
        1.  List of publications
        2.  Comments others have about this list of publications
    """

    _id          = db.ObjectIdField(required=True)

    items       = db.ListField(db.StringField(), required=True)
    comments    = db.ListField(db.IntField())

    def __str__(self):
        """ Returns a formatting string for printing publication lists """
        return """
                items: {}
                comments: {}
            """.format(self.items, self.comments)

class Interests(db.EmbeddedDocument):
    """
    Interests Data model behaves as follows:
        1.  List of interests
        2.  Comments others have about this list of interests
    """

    _id          = db.ObjectIdField(required=True)

    items       = db.ListField(db.StringField(), required=True)
    comments    = db.ListField(db.IntField())

    def __str__(self):
        """ Returns a formatting string for printing interest lists """
        return """
                items: {}
                comments: {}
            """.format(self.items, self.comments)

class Languages(db.EmbeddedDocument):
    """
    Languages Data model behaves as follows:
        1.  List of languages
        2.  Comments others have about this list of languages
    """

    _id          = db.ObjectIdField(required=True)

    items       = db.ListField(db.StringField(), required=True)
    comments    = db.ListField(db.IntField())

    def __str__(self):
        """ Returns a formatting string for printing language lists """
        return """
                items: {}
                comments: {}
            """.format(self.items, self.comments)

class Skills(db.EmbeddedDocument):
    """
    Skills Data model behaves as follows:
        1.  List of skills
        2.  Comments others have about this list of skills
    """

    _id          = db.ObjectIdField(required=True)    
    
    items       = db.ListField(db.StringField(), required=True)
    comments    = db.ListField(db.IntField())

    def __str__(self):
        """ Returns a formatting string for printing skills lists """
        return """
                items: {}
                comments: {}
            """.format(self.items, self.comments)

    def getAllSkills(self, expid , exp):
        return None

class Resume(db.Document):
    """
    Resume Data model behaves as follows:
        1.  User who owns the resume
        2.  All previous work experiences
        3.  All previous volunteer experiences
        4.  All previous education experiences
        5.  All previous awards won
        6.  List of skills (from work/volunteer/misc)
        7.  List of all publications
        8.  List of interests
        9.  List of known languages
        10. Tracker for comments in each section
        11. Tracker for todos in each section
        12. Version number/counter for resume
        13. Which edit number of the original resume this is (only fork)
        14. How many edits the document has (only non-fork)
    """

    meta = {'collection': 'resumes'}

    # _id          = db.ObjectIdField(required=True)    
    parent_user   = db.StringField(required=True)
    experience    = db.EmbeddedDocumentField(Experience, required=True)
    volunteer     = db.EmbeddedDocumentField(Volunteer, required=True)
    education     = db.EmbeddedDocumentField(Education, required=True)
    awards        = db.EmbeddedDocumentField(Awards, required=True)
    
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

    slug        = db.StringField(required=True)

    def __str__(self):
        """ Returns a formatting string for printing resumes """
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