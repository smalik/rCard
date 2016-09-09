"""
network.py: Sets up the friends page, where you can create your
network of resume acquaintances. Helps do 

__author__ = "Yash Patel"
__copyright__ = "Copyright 2016, Plytos Inc."

__license__ = "Free/Open"
__version__ = "1.0.0"
__maintainer__ = "Yash Patel"
__email__ = "ypatel@princeton.edu"
"""

from flask import (Blueprint, render_template, request, 
    redirect, url_for, g, jsonify, make_response)
from flask.views import View

from bson.objectid import ObjectId

from plytos.decorators import login_required
from plytos.models.person import Person
from plytos.views.get import (person_with_username, persons_with_ids)

class FriendView(View):
    decorators = [login_required]

    def get(self):
        return render_template('resumes/network.html')

    def post(self):
        dbUser = person_with_username(g.user.username)
        if "friend_user" in request.form:
            friend = person_with_username(
                request.form["friend_user"].strip())

            # makes sure not requesting someone who's already
            # been requested or an existing friend
            if dbUser._id not in friend.requests and \
                dbUser._id not in friend.friends: 
                
                friend.requests.append(dbUser._id)
                friend.switch_db("users")
                friend.save()
        return redirect(url_for('network_app.friends'))

    def dispatch_request(self):
        if request.method.lower() == 'get':
            return self.get()
        if request.method.lower() == 'post':
            return self.post()
        return "Improper method used: {}".format(request.method)

class RequestsView(View):
    decorators = [login_required]

    def get(self):
        dbUser = person_with_username(g.user.username)
        return render_template('resumes/friends.html',
            requests=persons_with_ids(dbUser.requests))

    def post(self):
        dbUser = person_with_username(g.user.username)
        if 'submit' in request.form and request.form['submit'] == 'accept':
            friend = person_with_username(request.form['user'])
            dbUser.requests.remove(friend._id)
            
            friend.friends.append(dbUser._id)
            friend.switch_db("users")
            friend.save()

            dbUser.friends.append(friend._id)
            dbUser.switch_db("users")
            dbUser.save()
        return redirect(url_for('network_app.friends'))

    def dispatch_request(self):
        if request.method.lower() == 'get':
            return self.get()
        if request.method.lower() == 'post':
            return self.post()
        return "Improper method used: {}".format(request.method)

class AddView(View):
    decorators = [login_required]

    def get(self):
        dbUser = person_with_username(g.user.username)
        return render_template('resumes/add.html',
            requests=persons_with_ids(dbUser.friends))

    def post(self):
        dbUser = person_with_username(g.user.username)
        if 'resume' in request.form:
            resume_id = ObjectId(request.form['resume'])

            dbUser.editing_resumes.append(resume_id)
            dbUser.switch_db("users")
            dbUser.save()
        return redirect(url_for('network_app.friends'))

    def dispatch_request(self):
        if request.method.lower() == 'get':
            return self.get()
        if request.method.lower() == 'post':
            return self.post()
        return "Improper method used: {}".format(request.method)

def setup_network(network_app):
    # for viewing the finalized resumes
    network_app.add_url_rule('/', view_func=FriendView.as_view('friends'), 
        methods=['GET', 'POST'])
    network_app.add_url_rule('/requests', 
        view_func=RequestsView.as_view('requests'), methods=['GET', 'POST'])
    network_app.add_url_rule('/add', 
        view_func=AddView.as_view('add'), methods=['GET', 'POST'])

network_app = Blueprint('network_app', __name__, template_folder='templates')
setup_network(network_app)