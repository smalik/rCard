"""
reset.py: Creates the model for PasswordReset, used for if
the User forgot his/her password

__author__ = "Yash Patel"
__copyright__ = "Copyright 2016, Plytos Inc."

__license__ = "Free/Open"
__version__ = "1.0.0"
__maintainer__ = "Yash Patel"
__email__ = "ypatel@princeton.edu"
"""

from plytos import db

class PasswordResetRequest(db.Document):
	_id = db.ObjectIdField()

	reset_code_hash = db.StringField(required=True) 
	user_id = db.StringField(required=True) 
	timestamp = db.DateTimeField(required=True)

	def __str__(self):
		return """
			reset_code_hash: {}
			user_id: {}
			timestamp: {}
		""".format(self.reset_code_hash, self.user_id, self.timestamp)