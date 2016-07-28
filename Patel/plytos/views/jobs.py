"""
jobs.py: Sets up the jobs page, where all the job posting will be
visible and populated

__author__ = "Yash Patel"
__copyright__ = "Copyright 2016, Plytos Inc."

__license__ = "Free/Open"
__version__ = "1.0.0"
__maintainer__ = "Yash Patel"
__email__ = "ypatel@princeton.edu"
"""

from flask import Blueprint, render_template, request, redirect, url_for

jobs_app = Blueprint('jobs_app', __name__, template_folder='templates')
@jobs_app.route('/', methods=["GET", "POST"])
def get_jobs():
    return render_template("index.html")