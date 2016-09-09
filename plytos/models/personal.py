"""
person.py: Creates the model for the personal info,
linked to both the user and resumes. Implemented in MongoDB

__author__ = "Yash Patel"
__copyright__ = "Copyright 2016, Plytos Inc."

__license__ = "Free/Open"
__version__ = "1.0.0"
__maintainer__ = "Yash Patel"
__email__ = "ypatel@princeton.edu"
"""

from plytos import db

class Location(db.EmbeddedDocument):
    """
    ToDosPerSection Data model behaves as follows:
        1.  First line of the address (required)
        2.  Second line of address
        3.  Zip code of location
        4.  City of location
        5.  Country of location
        6.  Region of location
    """

    _id          = db.ObjectIdField(required=True) 

    address1    = db.StringField(required=True)
    address2    = db.StringField()
    zipcode     = db.StringField()
    city        = db.StringField()
    country     = db.StringField()
    region      = db.StringField()

    def __str__(self):
        """ Returns a formatting string for printing locations """
        return """
                address1: {}
                address2: {}
                zipcode: {}
                city: {}
                country: {}
                region: {}
            """.format(self.address1, self.address2, self.zipcode, 
                self.city, self.country, self.region)

class SocialMediaItem(db.EmbeddedDocument):
    """
    SocialMediaItem Data model behaves as follows:
        1.  Name of the social media network (required)
        2.  Username on the network
        3.  URL of personal profile page (required)
    """

    _id          = db.ObjectIdField(required=True)

    network       = db.StringField(required=True)
    uname         = db.StringField()
    url           = db.StringField()

    def __str__(self):
        """ Returns a formatting string for printing social media """
        return """
                network: {}
                uname: {}
                url: {}
            """.format(self.network, self.uname, self.url)

class SocialProfile(db.EmbeddedDocument):
    """
    SocialProfile Data model behaves as follows:
        1.  List of all social media pages (required)
        2.  List of comments associated to profile
    """

    _id          = db.ObjectIdField(required=True)

    items       = db.ListField(db.EmbeddedDocumentField('SocialMediaItem'),
        required=True)
    comments    = db.ListField(db.ObjectIdField())

    def __str__(self):
        """ Returns a formatting string for printing profiles """
        return """
                items: {}
                comments: {}
            """.format(self.items, self.comments)

class Personal(db.EmbeddedDocument):
    """
    Personal Data model behaves as follows:
        1.  Username to whom the personal info belonds 
        2.  Location associated with the user
        3.  Social profiles of the user
        4.  First name (required)
        5.  Last name
        6.  Middle name
        7.  One-line description of person
        8.  User picture/snapshot
        9.  Phone number
        10. Homepage/URL of the user (i.e. profile)
        11. Text description self (extension of headline)
        12. List of comments associated to personal info
    """

    _id         = db.ObjectIdField(required=True)    
    
    location    = db.ListField(db.EmbeddedDocumentField('Location'))
    profiles    = db.ListField(db.EmbeddedDocumentField('SocialMediaItem'))

    firstName   = db.StringField()
    lastName    = db.StringField()
    middleName  = db.StringField()

    headline    = db.StringField()
    picture     = db.StringField()
    phone       = db.StringField()

    url         = db.StringField()

    def __str__(self):
        """ Returns a formatting string for printing personal attributes """
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
	            headline: {}
	        """.format(self.location, self.profiles, self.firstName, 
	            self.lastName, self.middleName, self.headline, self.picture, 
	            self.phone, self.url, self.headline)