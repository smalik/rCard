from app import db
from resumes import Resume, Person
from comments import Comment, CommentsPerSection, ToDosPerSection

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