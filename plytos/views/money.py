"""
money.py: Sets up the money page, where external payments can
be used to transfer and "create" in-game tokens

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

from plytos.decorators import login_required
from plytos.models.person import Person
from plytos.views.get import (person_with_username, resume_with_ids)

class MoneyView(View):
    decorators = [login_required]

    def get(self):
        # Listview only show particular user's resume
        creator = person_with_username(g.user.username)
        return "YOU FOOL"

    def dispatch_request(self):
        if request.method.lower() == 'get':
            return self.get()
        return "Improper method used: {}".format(request.method)

def setup_money(money_app):
    # for viewing the finalized resumes
    money_app.add_url_rule('/', view_func=MoneyView.as_view('money'), 
        methods=['GET'])

money_app = Blueprint('money_app', __name__, template_folder='templates')
setup_money(money_app)