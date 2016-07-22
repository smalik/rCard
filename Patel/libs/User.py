from flask.ext.login import UserMixin
from hashlib import md5 
from bson.objectid import ObjectId

from copy import deepcopy
import time

import resumes
import comments
from app import flask_bcrypt

# DEPRECATED
def make_resume(parent):
    resume = resumes.Resume()
    experience = resumes.Experience(
        _id = ObjectId(),
        items = [],
        comments = []
    )
    volunteer = resumes.Volunteer(
        _id = ObjectId(),
        items = [],
        comments = []
    )
    education = resumes.Education(
        _id = ObjectId(),
        items = [],
        comments = []
    )
    awards = resumes.Awards(
        _id = ObjectId(),
        items = [],
        comments = []
    )
    pubs = resumes.Publications(
        _id = ObjectId(),
        items = [],
        comments = []
    )
    interests = resumes.Interests(
        _id = ObjectId(),
        items = [],
        comments = []
    )
    languages = resumes.Languages(
        _id = ObjectId(),
        items = [],
        comments = []
    )
    skills = resumes.Skills(
        _id = ObjectId(),
        items = [],
        comments = []
    )
    
    comments_per_section = comments.CommentsPerSection(
        _id = ObjectId(),
        num_comments = 0,
        index_num = 0,
        section_name = ""
    )
    todos_per_section = comments.ToDosPerSection(
        _id = ObjectId(),
        num_todos = 0,
        index_num = 0,
        section_name = ""
    )
    
    resume._id = ObjectId()
    resume.experience = experience
    resume.volunteer = volunteer
    resume.education = education
    resume.awards = awards
    resume.pubs = pubs
    resume.interests = interests
    resume.languages = languages
    resume.skills = skills

    resume.comments_per_section = comments_per_section
    resume.todos_per_section = todos_per_section

    resume.version = 0
    resume.numEdits = 0
    resume.editDt = []
    resume.slug = ""

    return resume

class User(UserMixin):
    def __init__(self, email=None, password_hash=None, 
        active=True, username=None):
        self.email = email
        self.password_hash = password_hash
        self.active = active
        self.username = username
        self.isAdmin = False
        self.id = ObjectId()

    def __str__(self):
        return """
            email: {}
            password_hash: {}
            active: {}
            username: {}
            isAdmin: {}
            id: {}""".format(self.email, self.password_hash, 
                self.active, self.username, self.isAdmin, self.id)

    def is_active(self):
        return self.active

    def get_id(self):
        return self.id

    def is_authenticated(self):
        return True

    def is_anonymous(self):
        return False

    def save(self):
        new_user = resumes.Person()
        new_user._id = ObjectId()
        new_user.email = self.email
        new_user.password_hash = self.password_hash
        new_user.active = self.active
        new_user.username = self.username
        new_user.info = ""

        new_user.final_resumes = []
        new_user.working_resumes = []

        new_user.current_edits = []
        new_user.editing_resumes = []
        new_user.comments = []

        new_user.skills = resumes.Skills(
           _id = ObjectId(),
           items = [],
           comments = []
        )

        new_user.save()
        return self.id

    def get_by_id(self, id):
        dbUser = resumes.Person.objects.with_id(id)
        if dbUser:
            self.email = dbUser.email
            self.username = dbUser.username
            self.active = dbUser.active
            self.id = dbUser.id

            return self
        else:
            return None

    def reset_password(self, user_id, password):
        dbUser = resumes.Person.objects.with_id(user_id)
        dbUser.password_hash = password
        print("Trying to change password of user id = {} ".format(user_id))
        dbUser.save()
        print("changed password of user id = {} ".format(user_id))
        return self

    def get_by_email_w_password(self, email):

        try:
            dbUser = resumes.Person.objects.get_or_404(email=email)
            
            if dbUser:
                self.email = dbUser.email
                self.username = dbUser.username
                self.active = dbUser.active
                self.password_hash = dbUser.password_hash
                self.id = dbUser.id
                
                return self
            else:
                return None
        except:
            print("error retrieving user")
            return None

    @classmethod
    def avatar(self, email, size):
        try:
            return 'http://www.gravatar.com/avatar/{}?d=mm&s={}'.format(
                md5(email).hexdigest(), str(size))
        except:
            return None

    def get_by_username(self, uname):
        try:
            dbUser = resumes.Person.objects.get_or_404(username=uname)
            if dbUser:
                self.email = dbUser.email
                self.username = dbUser.username
                self.active = dbUser.active
                self.password_hash = dbUser.password_hash
                self.id = dbUser.id
                
                return self
            else:
                return None
        except:
            print("error retrieving user")
            return None