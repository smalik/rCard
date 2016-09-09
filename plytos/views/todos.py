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

from bson.objectid import ObjectId

from plytos.forms import TodoForm
from plytos.decorators import login_required
from plytos.models.todo import ToDo
from plytos.views.get import (person_with_username, resume_with_id,
    todos_with_ids)

class ListTodoView(View):
    #Also need a decorator to verify this is the owner of resume
    decorators = [login_required]

    def get(self):
        dbUser = person_with_username(g.user.username)
        return render_template("resumes/list_todos.html", 
            resumes=dbUser.working_resumes)

    def dispatch_request(self):
        if request.method.lower() == 'get':
            return self.get()
        return "Improper method used: {}".format(request.method)

class TodoView(View):
    #Also need a decorator to verify this is the owner of resume
    decorators = [login_required]

    def get_context(self):
        todo_form = TodoForm()
        context = {
            "todo_form": todo_form
        }
        return context

    def get(self, _id):
        context = self.get_context()
        todo_form = context.get('todo_form')
        resume = resume_with_id(_id)

        return render_template('resumes/todos.html', todo_form=todo_form,
            incomplete_todos=todos_with_ids(resume.incomplete_todos),
            complete_todos=todos_with_ids(resume.complete_todos))

    def post(self, _id):
        resume = resume_with_id(_id)
        if "payload" in request.form:
            todo           = ToDo()
            todo._id       = ObjectId()
            todo.resume_id = _id
            todo.payload   = request.form["payload"]
            
            todo.switch_db("todos")
            todo.save()

            resume.incomplete_todos.append(todo._id)
            resume.switch_db("resumes")
            resume.save()

        elif "todo" in request.form:
            completed_todo = ObjectId(request.form["todo"])

            resume.incomplete_todos.remove(completed_todo)
            resume.complete_todos.append(completed_todo)
            resume.switch_db("resumes")
            resume.save()

        return redirect(url_for("resume_app.list_todos", slug=str(_id)))

    def dispatch_request(self, slug):
        _id = ObjectId(slug)
        if request.method.lower() == 'get':
            return self.get(_id)
        if request.method.lower() == 'post':
            return self.post(_id)
        return "Improper method used: {}".format(request.method)

def setup_todos(resume_app):
    resume_app.add_url_rule('/todos', view_func=ListTodoView.as_view('list_todos'), 
        methods=['GET'])
    resume_app.add_url_rule('/todos/<slug>', view_func=TodoView.as_view('todos'), 
        methods=['GET', 'POST'])