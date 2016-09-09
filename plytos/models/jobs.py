"""
jobs.py: Creates the model for the Job, used for 
streaming any online listings. Implemented in MongoDB

__author__ = "Yash Patel"
__copyright__ = "Copyright 2016, Plytos Inc."

__license__ = "Free/Open"
__version__ = "1.0.0"
__maintainer__ = "Yash Patel"
__email__ = "ypatel@princeton.edu"
"""

from datetime import datetime
from plytos import db

class Job(db.Document):
    """
    Job description Data model behaves as follows:
        1.  Company Name (required)
        2.  Job Title
        3.  Paid position
        4.  Pay range 
        5.  Skills requested
        6.  Job Description
        7.  Quaifications
        8.  Start Date
        9.  Location
        10. Work Remotely
        11. Benefits
    """
    meta = {'collection': 'jobs'}

    _id         = db.ObjectIdField(required=True)

    companyName = db.StringField(required=True)
    title       = db.StringField()

    isPaid      = db.BooleanField()
    minPay      = db.FloatField()
    maxPay      = db.FloatField()
    skills      = db.ListField(db.FloatField())

    description = db.StringField()
    quals       = db.StringField()
    startDt     = db.DateTimeField()

    isRemote    = db.BooleanField()
    benefits    = db.FloatField()

    def __str__(self):
        """ Returns a formatting string for printing jobs """
        return """
            id: {}
            companyName: {}
            title: {}
            isPaid: {}
            minPay: {}
            maxPay: {}
            skills: {}
            description: {}
            quals: {}
            startDt: {}
            isRemote: {}
            benefits: {}
            skills: {}
        """.format(self._id, self.companyName, self.title, self.isPaid, 
            self.minPay, self.maxPay, self.skills, self.description, 
            self.quals, self.startDt, self.isRemote, self.benefits,
            self.skills)