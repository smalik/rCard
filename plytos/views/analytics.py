"""
analytics.py: Setsup the models for the analytics,
specifically used for charting out the path of a person's
career based on past trends and experience

__author__ = "Yash Patel"
__copyright__ = "Copyright 2016, Plytos Inc."

__license__ = "Free/Open"
__version__ = "1.0.0"
__maintainer__ = "Yash Patel"
__email__ = "ypatel@princeton.edu"
"""

from flask import (Blueprint, render_template, request, 
    redirect, url_for, g, jsonify, make_response)
from flask.views import MethodView
from flask.ext.login import login_required

import json

from plytos.models.person import Person

analytics_app = Blueprint('analytics_app', __name__, 
    template_folder='templates', static_folder='static', 
    static_url_path='/static')

class AnalyticsView(MethodView):
    decorators = [login_required]

    def get(self):
        #Get reference of current user and send it to template
        #Should only send relevant stats based on user
        curr_user = Person.objects.get_or_404(email=g.user.email)
        return render_template('analytics/dash.html', user=curr_user)

class SkillAPI(MethodView):
    decorators = [login_required]

    def get(self, occupation_id=None):
        pass

class RelatedOccupationAPI(MethodView):
    decorators = [login_required]

    def get(self, occupation_id=None):
        pass

class OccupationLocationAPI(MethodView):
    decorators = [login_required]

    def get(self, occupation_id=None):
        pass

analytics_app.add_url_rule('/', 
    view_func=AnalyticsView.as_view('analytics'), methods=['GET'])