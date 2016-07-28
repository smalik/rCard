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

"""
Job description Data model behaves as follows:
    1.  Company Name
    2.  Job Title
    3.  Paid position (Yes or No)
    4.  Pay range (min, max)
    5.  Skills requested
    6.  Job Description
    7.  Quaifications
    8.  Start Date (date, ASAP)
    9.  Location
    10. Work Remotely (Yes or No)
    11. Benefits (as tags)
"""
class JobDescription(db.Document):
    _id         = db.ObjectIdField()

    companyName = db.StringField()
    title       = db.StringField()

    isPaid      = db.ListField(db.BooleanField())
    minPay      = db.ListField(db.FloatField())
    maxPay      = db.ListField(db.FloatField())
    skills      = db.ListField(db.FloatField())

    description = db.StringField()
    quals       = db.StringField()
    startDt     = db.DateTimeField()

    isRemote    = db.ListField(db.BooleanField())
    benefits    = db.ListField(db.FloatField())
    skills      = db.ListField(db.FloatField())