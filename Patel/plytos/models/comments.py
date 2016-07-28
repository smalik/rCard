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

"""
Comments behave as follows:
     1. Click on a comment button on the card.
     2. A comment card pops up with:
         i.      commenter pic
         ii.     commenter username
         iii.    comment text area
         iv.     like button
         v.      downvote button
         vi.     submit button (optional)
     3. User adds their comment text (limited to 240 chars)
     4. Threaded to one level
"""

"""
Base comment class that other commenting classes inherit.  We want to capture 
the comment author, likes, downvotes, comment text, comment date, and what 
topic the comment is about
"""
class Comment(db.EmbeddedDocument):
    _id         = db.ObjectIdField()

    # user ID from Person class of contributor
    author_user = db.StringField()
    createDt    = db.DateTimeField()

    # Topic of comment (e.g.  grammar, clarity, etc...)
    topic       = db.StringField()

    # Section this comment is bound to
    section     = db.StringField()

    # how many people upvoted/downvoted the comment posted in payload
    upvote       = db.IntField()
    downvote     = db.IntField()

    # actual comment
    payload      = db.StringField()

    def __str__(self):
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

class CommentsPerSection(db.EmbeddedDocument):
    _id         = db.ObjectIdField()

    num_comments = db.IntField()
    index_num    = db.IntField()
    section_name = db.StringField()

    def __str__(self):
        return """
            num_comments: {}
            index_num: {}
            section_name: {}
        """.format(self.num_comments, self.index_num, self.section_name)
    
class ToDosPerSection(db.EmbeddedDocument):
    _id         = db.ObjectIdField()

    num_todos    = db.IntField()
    index_num    = db.IntField()
    section_name = db.StringField()

    def __str__(self):
        return """
            num_todos: {}
            index_num: {}
            section_name: {}
        """.format(self.num_todos, self.index_num, self.section_name)