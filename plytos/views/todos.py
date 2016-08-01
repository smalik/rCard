"""
todos.py: Sets up a view containing a list of items that the user
pinned as being "todos" (i.e. next steps) for editing his/her resume.

__author__ = "Yash Patel"
__copyright__ = "Copyright 2016, Plytos Inc."

__license__ = "Free/Open"
__version__ = "1.0.0"
__maintainer__ = "Yash Patel"
__email__ = "ypatel@princeton.edu"
"""

from flask import (render_template, request, redirect, 
    url_for, g, abort, session)
from flask.views import View

from plytos.decorators import login_required
from plytos.models.resume import Resume

class TodoView(View):
    #Also need a decorator to verify this is the owner of resume
    decorators = [login_required]

    def post(self, slug=None):
        x = json.loads(request.data)
        # This is a limitation of logic to generate slugs
        # should really generate a unique slug
        resume = Resume.objects.get_or_404(slug=x['slug'].replace("%20", " "))

        for section in x['sections']:
            for todo in resume.todos_per_section:
                if todo.section_name.lower() == section["section_name"].lower():
                    todo.num_todos = section["value"]
        
        resume.parent.save()
        return "200"

    def dispatch_request(self, slug):
        if request.method.lower() == 'post':
            return self.post(slug)
        return "Improper method used: {}".format(request.method)

def setup_todos(resume_app):
    resume_app.add_url_rule('/todos', view_func=TodoView.as_view('todos'), 
        methods=['POST'])