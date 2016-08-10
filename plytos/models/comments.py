"""
comments.py: Creates the model for the comment system,
namely the comment and todos objects. Implemented in MongoDB

__author__ = "Yash Patel"
__copyright__ = "Copyright 2016, Plytos Inc."

__license__ = "Free/Open"
__version__ = "1.0.0"
__maintainer__ = "Yash Patel"
__email__ = "ypatel@princeton.edu"
"""

from plytos import db

class Comment(db.EmbeddedDocument):
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

    author_user = db.StringField(required=True)
    createDt    = db.DateTimeField()

    topic       = db.StringField()

    section     = db.StringField(required=True)

    upvote       = db.IntField(required=True)
    downvote     = db.IntField(required=True)
    payload      = db.StringField(required=True)

    def __str__(self):
        """ Returns a formatting string for printing comments """
        return """
            author: {}
            createDt: {}
            topic: {}
            section: {}
            upvote: {}
            downvote: {}
            payload: {}
        """.format(self.author_user, self.createDt, self.topic, 
            self.section, self.upvote, self.downvote, self.payload)

class ToDo(db.EmbeddedDocument):
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

    createDt    = db.DateTimeField()

    topic       = db.StringField()
    section     = db.StringField(required=True)
    payload      = db.StringField(required=True)

    def __str__(self):
        """ Returns a formatting string for printing comments """
        return """
            createDt: {}
            topic: {}
            section: {}
            payload: {}
        """.format(self.createDt, self.topic, self.section, self.payload)

class CommentsPerSection(db.EmbeddedDocument):
    """
    CommentsPerSection Data model behaves as follows:
        1.  How many comments included in the section (required)
        2.  ID of the section being tracked
        3.  Name of section being tracked (required)
    """

    _id         = db.ObjectIdField(required=True)

    num_comments = db.IntField(required=True)
    index_num    = db.IntField()
    section_name = db.StringField(required=True)

    def __str__(self):
        """ Returns a formatting string for printing objects that
        maintain the number of comments in a given section
        """
        return """
            num_comments: {}
            index_num: {}
            section_name: {}
        """.format(self.num_comments, self.index_num, self.section_name)
    
class ToDosPerSection(db.EmbeddedDocument):
    """
    ToDosPerSection Data model behaves as follows:
        1.  How many to-dos included in the section (required)
        2.  ID of the section being tracked
        3.  Name of section being tracked (required)
    """

    _id         = db.ObjectIdField(required=True)

    num_todos    = db.IntField(required=True)
    index_num    = db.IntField()
    section_name = db.StringField(required=True)

    def __str__(self):
        """ Returns a formatting string for printing objects that
        maintain the number of to-dos in a given section
        """
        return """
            num_todos: {}
            index_num: {}
            section_name: {}
        """.format(self.num_todos, self.index_num, self.section_name)