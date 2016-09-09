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

from mongoengine.queryset import QuerySet

from plytos import db
from plytos.models.personal import Personal
from plytos.models.comments import CommentsPerSection
from plytos.models.todo import ToDosPerSection

class VolunteerItem(db.EmbeddedDocument):
    """
    VolunteerItem Data model behaves as follows:
        1.  Organization at which user did this volunteer work (required)
        2.  Title/Type of volunteering
        3.  Date volunteering started
        4.  Date volunteering ended
        5.  URL of the volunteer organization/opportunity
        6.  Summary description of experience
        7.  List of highlights from volunteer experience
    """

    _id          = db.ObjectIdField(required=True)

    organization     = db.StringField(required=True)
    position         = db.StringField()
    startDate        = db.DateTimeField()
    endDate          = db.DateTimeField()
    website          = db.StringField()
    summary          = db.StringField()

    highlights    = db.ListField(db.StringField())

    # used to identify who is responsible for the item
    parent_id     = db.ObjectIdField(required=True)
    edit_ids      = db.ListField(db.ObjectIdField(required=True))

    def __str__(self):
        """ Returns a formatting string for printing volunteer instances """
        return """
            parent_id: {}
            organization: {}
            position: {}
            startDate: {}
            endDate: {}
            website: {}
            summary: {}
            highlights: {}
        """.format(self.parent_id, self.organization, self.position, 
            self.startDate, self.endDate, self.website, 
            self.summary, self.highlights)

class WorkItem(db.EmbeddedDocument):
    """
    WorkItem Data model behaves as follows:
        1.  Organization at which user did this work work (required)
        2.  Title/Type of volunteering
        3.  Date volunteering started
        4.  Date volunteering ended
        5.  URL of the volunteer organization/opportunity
        6.  Summary description of experience
        7.  List of highlights from volunteer experience
        8.  Skills gained as a result of work
    """

    _id           = db.ObjectIdField(required=True)

    company       = db.StringField(required=True)
    position      = db.StringField()
    startDate     = db.DateTimeField()
    endDate       = db.DateTimeField()
    website       = db.StringField()
   # summary       = db.StringField()

    highlights    = db.ListField(db.StringField())

    # used to identify who is responsible for the item
    parent_id     = db.ObjectIdField(required=True)
    edit_ids      = db.ListField(db.ObjectIdField(required=True))

    def __str__(self):
        """ Returns a formatting string for printing work instances """
        return """
                parent_id: {}
                company: {}
                startDate: {}
                endDate: {}
                position: {}
                website: {}
                highlights: {}
            """.format(self.parent_id, self.company, self.startDate, 
                self.endDate, self.position, self.website, self.highlights)

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

    institution    = db.StringField(required=True)
    studyType      = db.StringField()
    area           = db.StringField()
    startDate      = db.DateTimeField()
    endDate        = db.DateTimeField()
    gpa            = db.FloatField()

    courses        = db.ListField(db.StringField())

    # used to identify who is responsible for the item
    parent_id     = db.ObjectIdField(required=True)
    edit_ids      = db.ListField(db.ObjectIdField(required=True))

    def push_course(self, course):
        self.courses.append(course)

    def __str__(self):
        """ Returns a formatting string for printing education instances """
        return """
                parent_id: {}
                institution: {}
                studyType: {}
                area: {}
                startDate: {}
                endDate: {}
                gpa: {}
                courses: {}
            """.format(self.parent_id, self.institution, self.studyType, self.area, 
                self.startDate, self.endDate, self.gpa, self.courses)

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
    awarder      = db.StringField()
    summary      = db.StringField()

    # used to identify who is responsible for the item
    parent_id     = db.ObjectIdField(required=True)
    edit_ids      = db.ListField(db.ObjectIdField(required=True))

    def __str__(self):
        """ Returns a formatting string for printing award instances """
        return """
                parent_id: {}
                title: {}
                date: {}
                issuer: {}
                desc: {}
            """.format(self.parent_id, self.title, self.date, 
                self.awarder, self.summary)

class SkillItem(db.EmbeddedDocument):
    """
    SkillItem Data model behaves as follows:
        1.  Name of the skill possessed
        2.  Level of performance of this skill (expert/intermediate...)
    """

    _id          = db.ObjectIdField(required=True)

    name         = db.StringField(required=True)
    level        = db.StringField()
    
    # used to identify who is responsible for the item
    parent_id     = db.ObjectIdField(required=True)
    edit_ids      = db.ListField(db.ObjectIdField(required=True))

    def __str__(self):
        """ Returns a formatting string for printing skill instances """
        return """
            name: {}
            level: {}
        """.format(self.name, self.level)

class PublicationItem(db.EmbeddedDocument):
    """
    PublicationItem Data model behaves as follows:
        1.  Name of the publication
        2.  Who published the work (i.e. which journal)
        3.  When the work was published
        4.  The URL or website where it can be accessed
        5.  A summary/abstract of the paper
    """

    _id          = db.ObjectIdField(required=True)

    name            = db.StringField(required=True)
    publisher       = db.StringField()
    releaseDate    = db.DateTimeField()
    website         = db.StringField()
    summary         = db.StringField()

    # used to identify who is responsible for the item
    parent_id     = db.ObjectIdField(required=True)
    edit_ids      = db.ListField(db.ObjectIdField(required=True))

    def __str__(self):
        """ Returns a formatting string for printing publication instances """
        return """
            name: {}
            publisher: {}
            releaseDate: {}
            website: {}
            summary: {}
        """.format(self.name, self.publisher, 
            self.releaseDate, self.website, self.summary)

class InterestItem(db.EmbeddedDocument):
    """
    InterestItem Data model behaves as follows:
        1.  Name of the interest
    """

    _id          = db.ObjectIdField(required=True)

    name         = db.StringField(required=True)

    # used to identify who is responsible for the item
    parent_id     = db.ObjectIdField(required=True)
    edit_ids      = db.ListField(db.ObjectIdField(required=True))

    def __str__(self):
        """ Returns a formatting string for printing interest instances """
        return """
            name: {}
        """.format(self.name)

class LanguageItem(db.EmbeddedDocument):
    """
    LanguageItem Data model behaves as follows:
        1.  Which language you have fluency in
        2.  The level of fluency of said language
    """

    _id          = db.ObjectIdField(required=True)

    language     = db.StringField(required=True)
    fluency      = db.StringField(required=True)

    # used to identify who is responsible for the item
    parent_id     = db.ObjectIdField(required=True)
    edit_ids      = db.ListField(db.ObjectIdField(required=True))

    def __str__(self):
        """ Returns a formatting string for printing language instances """
        return """
            language: {}
            fluency: {}
        """.format(self.language, self.fluency)

class Work(db.EmbeddedDocument):
    """
    Work Data model behaves as follows:
        1.  List of work experiences
        2.  Comments others have about this list of experiences
    """
    
    _id          = db.ObjectIdField(required=True)

    items       = db.ListField(db.EmbeddedDocumentField('WorkItem'))
    comments    = db.ListField(db.ObjectIdField())

    def __str__(self):
        """ Returns a formatting string for printing experience lists """
        return """
                _id: {}
                items: {}
                comments: {}
            """.format(self._id, self.items, self.comments)

class Volunteer(db.EmbeddedDocument):
    """
    Volunteer Data model behaves as follows:
        1.  List of volunteer experiences
        2.  Comments others have about this list of experiences
    """

    _id          = db.ObjectIdField(required=True)

    items       = db.ListField(db.EmbeddedDocumentField('VolunteerItem'))
    comments    = db.ListField(db.ObjectIdField())

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
    comments    = db.ListField(db.ObjectIdField())

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
    comments    = db.ListField(db.ObjectIdField())

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
    
    items       = db.ListField(db.EmbeddedDocumentField('PublicationItem'))
    comments    = db.ListField(db.ObjectIdField())

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
    
    items       = db.ListField(db.EmbeddedDocumentField('InterestItem'))
    comments    = db.ListField(db.ObjectIdField())

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
    
    items       = db.ListField(db.EmbeddedDocumentField('LanguageItem'))
    comments    = db.ListField(db.ObjectIdField())

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
    
    items       = db.ListField(db.EmbeddedDocumentField('SkillItem'))
    comments    = db.ListField(db.ObjectIdField())

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

    _id          = db.ObjectIdField(required=True)    

    # ID of resume from which branched; None if original resume
    parent_resume = db.ObjectIdField()
    parent_user   = db.ObjectIdField()

    personal      = db.EmbeddedDocumentField(Personal, required=True)
    work          = db.EmbeddedDocumentField(Work, required=True)
    volunteer     = db.EmbeddedDocumentField(Volunteer, required=True)
    education     = db.EmbeddedDocumentField(Education, required=True)
    awards        = db.EmbeddedDocumentField(Awards, required=True)
    
    skills        = db.EmbeddedDocumentField(Skills, required=True)
    publications  = db.EmbeddedDocumentField(Publications, required=True)
    interests     = db.EmbeddedDocumentField(Interests, required=True)
    languages     = db.EmbeddedDocumentField(Languages, required=True)

    comments_per_section = db.EmbeddedDocumentField(CommentsPerSection)
    todos_per_section    = db.EmbeddedDocumentField(ToDosPerSection)

    complete_todos       = db.ListField(db.ObjectIdField())
    incomplete_todos     = db.ListField(db.ObjectIdField())

    comments       = db.ListField(db.ObjectIdField())
    edit_date      = db.ListField(db.DateTimeField())

    def __str__(self):
        """ Returns a formatting string for printing resumes """
        return """
            _id: {}
            parent_resume: {}
            parent_user: {}

            personal: {}
            work: {}
            volunteer: {}
            education: {}
            skills: {}
            awards: {}
            publications: {}
            interests: {}
            languages: {}

            comments_per_section: {}
            todos_per_section: {}

            complete_todos: {}
            incomplete_todos: {}

            comments: {}
            edit_date: {}
        """.format(self._id, self.parent_resume, self.parent_user, 
            self.personal, self.work, self.volunteer, self.education, 
            self.skills, self.awards, self.publications, self.interests, 
            self.languages, self.comments_per_section, 
            self.todos_per_section, self.complete_todos,
            self.incomplete_todos, self.comments, self.edit_date)