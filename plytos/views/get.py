"""
auth.py: File of helper methods used to retrieve objects from DB.
Takes care of the alterate DBs to which objects are saved

__author__ = "Yash Patel"
__copyright__ = "Copyright 2016, Plytos Inc."

__license__ = "Free/Open"
__version__ = "1.0.0"
__maintainer__ = "Yash Patel"
__email__ = "ypatel@princeton.edu"
"""

from mongoengine.queryset import QuerySet

from plytos.models.person import Person
from plytos.models.jobs import Job
from plytos.models.resume import Resume
from plytos.models.comments import Comment
from plytos.models.todo import ToDo

def _generic_get(cls, db):
    """Returns group of objects in DB requested. Must all be
    of the type specified with cls

    Keyword arguments:
    cls (object) -- Class of objects stored in DB
    db (string)  -- Name of the DB being retrieved from
    """
    group = cls.switch_db(cls(), db)
    return QuerySet(cls, group._get_collection())

def _generic_id_get(cls, db, _id):
    return _generic_get(cls, db).filter(_id=_id)[0]

def person_with_username(username):
    """Returns DB user object associated to the passed in username

    Keyword arguments:
    username (string) -- Name of the user to be retrieved
    """
    person = _generic_get(Person, 'users').filter(username=username)[0]
    if person: 
        return person
    return None

def resume_with_slug(slug):
    """Returns DB resume object associated to the passed in _id

    Keyword arguments:
    _id (binary) -- ObjectID object being retrieved
    """
    return _generic_get(Resume, 'resumes').filter(slug=slug)[0]

def person_with_id(_id):
    """Returns DB person object associated to the passed in _id

    Keyword arguments:
    _id (binary) -- ObjectID object being retrieved
    """
    return _generic_id_get(Person, 'users', _id)
    
def persons_with_ids(ids):
    """Returns list of DB user objects associated to the passed 
    in list of usernames

    Keyword arguments:
    usernames (list(string)) -- Name of the users to be retrieved
    """
    persons = []
    for _id in ids:
        person = person_with_id(_id)
        if person:
            persons.append(person)
    return persons

def resume_with_id(_id):
    """Returns DB resume object associated to the passed in _id

    Keyword arguments:
    _id (binary) -- ObjectID object being retrieved
    """
    return _generic_id_get(Resume, 'resumes', _id)

def resume_with_ids(ids):
    """Returns array of DB resume objects associated to the 
    passed in _ids array. Will return empty array if ids empty

    Keyword arguments:
    ids (list(binary)) -- list of ObjectID object being retrieved
    """
    resumes = []
    for resume_id in ids:
        resumes.append(resume_with_id(resume_id))
    return resumes

def todo_with_id(_id):
    """Returns todo object associated to the passed in _id

    Keyword arguments:
    _id (binary) -- ObjectID object being retrieved
    """
    return _generic_id_get(ToDo, 'todos', _id)

def comments_with_id(_id, comment_type):
    """Returns resume comment object associated to the passed in _id
    from the DB corresponding to the comment_type

    Keyword arguments:
    _id (binary) -- ObjectID object being retrieved
    comment_type (str) -- Name of the type of comment being retrieved
    """
    return _generic_id_get(Comment, '{}_comments'.format(comment_type), _id)

def todos_with_id(_id):
    """Returns ToDo object associated to the passed in _id

    Keyword arguments:
    _id (binary) -- ObjectID object being retrieved
    """
    return _generic_id_get(ToDo, 'todos', _id)

def todos_with_ids(ids):
    """Returns ToDo objects associated to the passed in ids list

    Keyword arguments:
    ids (list(binary)) -- list of ObjectID objects being retrieved
    """
    todos = []
    for _id in ids:
        todo = todos_with_id(_id)
        if todo:
            todos.append(todo)
    return todos