"""
todo.py: Creates the model for the todo system. 
Implemented in MongoDB

__author__ = "Yash Patel"
__copyright__ = "Copyright 2016, Plytos Inc."

__license__ = "Free/Open"
__version__ = "1.0.0"
__maintainer__ = "Yash Patel"
__email__ = "ypatel@princeton.edu"
"""

from plytos import db

class ToDo(db.Document):
    """
    Comment Data model behaves as follows:
        1.  ID of the resume to which it is associated (required)
        2.  When the todo was posted
        3.  What topic the todo is about (required)
    """

    meta = {'collection': 'todos'}

    _id         = db.ObjectIdField(required=True)
    resume_id   = db.ObjectIdField(required=True)

    createDt    = db.DateTimeField()
    payload     = db.StringField(required=True)

    def __str__(self):
        """ Returns a formatting string for printing comments """
        return """
            createDt: {}
            payload: {}
        """.format(self.createDt, self.payload)

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