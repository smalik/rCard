"""
comments.py: Creates the model for the comment system. 
Implemented in MongoDB

__author__ = "Yash Patel"
__copyright__ = "Copyright 2016, Plytos Inc."

__license__ = "Free/Open"
__version__ = "1.0.0"
__maintainer__ = "Yash Patel"
__email__ = "ypatel@princeton.edu"
"""

from plytos import db

class Comment(db.Document):
    """
    Comment Data model behaves as follows:
        1.  User name of commenter (required)
        2.  When the comment was posted (required)
        3.  What topic the comment is about (heading)
        4.  Where the comment is posted (required)
        5.  How many upvotes ("likes") comment received (required)
        6.  How many downvotes ("dislikes") received (required)
        7.  The text content of the comment (required)
    """

    meta = {'collection': 'comments'}

    _id         = db.ObjectIdField(required=True)

    author_user = db.ObjectIdField(required=True)
    createDt    = db.DateTimeField()

    topic       = db.StringField()
    section     = db.StringField()

    upvote       = db.IntField(required=True)
    downvote     = db.IntField(required=True)
    payload      = db.StringField(required=True)

    def __str__(self):
        """ Returns a formatting string for printing comments """
        return """
            id: {}
            author: {}
            createDt: {}
            topic: {}
            section: {}
            upvote: {}
            downvote: {}
            payload: {}
        """.format(self._id, self.author_user, self.createDt, self.topic, 
            self.section, self.upvote, self.downvote, self.payload)

class CommentsPerSection(db.EmbeddedDocument):
    """
    CommentsPerSection Data model behaves as follows:
        1.  How many comments included in the section (required)
        2.  ID of the section being tracked
        3.  Name of section being tracked (required)
    """

    _id         = db.ObjectIdField(required=True)

    work           = db.IntField(required=True)
    volunteer      = db.IntField(required=True)
    education      = db.IntField(required=True)
    awards         = db.IntField(required=True)
    skills         = db.IntField(required=True)
    publications   = db.IntField(required=True)
    interests      = db.IntField(required=True)
    languages      = db.IntField(required=True)

    def __str__(self):
        """ Returns a formatting string for printing objects that
        maintain the number of comments in a given section
        """
        return """
                work: {}
                volunteer: {}
                education: {}
                awards: {}
                skills: {}
                publications: {}
                interests: {}
                languages: {}
        """.format(self.work, self.volunteer, self.education, 
                self.awards, self.skills, self.publications, 
                self.interests, self.languages)