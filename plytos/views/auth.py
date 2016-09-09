"""
auth.py: Sets up the basic functionality of the app, namely
the login, registration, and logout features, namely all those
under the /user/ extension. Creates these in the "Login",
"Register", and "Logout" pages

__author__ = "Yash Patel"
__copyright__ = "Copyright 2016, Plytos Inc."

__license__ = "Free/Open"
__version__ = "1.0.0"
__maintainer__ = "Yash Patel"
__email__ = "ypatel@princeton.edu"
"""

from flask import (Blueprint, render_template, request, current_app, flash,
                   redirect, url_for, session, g)
from flask.views import View
from flask.ext.login import (login_user, UserMixin,
    logout_user, confirm_login, current_user)
from flask.ext.principal import Identity, AnonymousIdentity, identity_changed
from flask.ext.mail import Message
from bson.objectid import ObjectId

from uuid import uuid4
from datetime import datetime
import json

from plytos import login_manager, flask_bcrypt, mail, app
from plytos.decorators import async, login_required

from plytos.oauth import OAuthSignIn
from plytos.models.resume import Skills
from plytos.models.comments import Comment
from plytos.models.person import Person
from plytos.models.personal import Location, SocialMediaItem, Personal
from plytos.models.reset import PasswordResetRequest
from plytos.forms import (LoginForm, RegisterForm, ForgotForm, ResetPassForm,
    BasicForm, LocationForm, SocialProfileForm)

from plytos.views.get import person_with_username

MIN_PASSWORD_LENGTH = 4

@login_manager.unauthorized_handler
def unauthorized_callback():
    flash('Please login', 'warning')
    return redirect('/login?next=' + request.path)

@login_manager.user_loader
def load_user(uname):
    if uname is None or uname.strip() == "None":
        return redirect(url_for('auth_app.home'))
    user = person_with_username(uname)
    return user

# General Request Handlers
@app.before_request
def before_request():
    """Sets up the global user object to be retrieved that is
    associated with the current session user
    """
    if "user_id" in session and session["user_id"]:
        g.user = person_with_username(username=session["user_id"])
    else:
        g.user = current_user

@app.route('/authorize/<provider>')
def oauth_authorize(provider):
    if not current_user.is_anonymous:
        return redirect(url_for('auth_app.home'))
    oauth = OAuthSignIn.get_provider(provider)
    return oauth.authorize()

@app.route('/callback/<provider>')
def oauth_callback(provider):
    if not current_user.is_anonymous:
       return redirect(url_for('auth_app.home'))
    oauth = OAuthSignIn.get_provider(provider)
    social_id, username, email = oauth.callback()
    if social_id is None:
        flash('Authentication failed.')
        return redirect(url_for('auth_app.home'))
    
    user = create_user(email, social_id)
    login_user(user, True)
    session["user_id"] = username
    
    return redirect(url_for('auth_app.home'))

def create_user(email, username, password_hash=None):
    user = Person()
            
    user._id = ObjectId()
    user.email = email
    user.password_hash = password_hash
    user.active = True
    user.username = username
    
    user.final_resumes = []
    user.working_resumes = []

    user.current_edits = []
    user.editing_resumes = []

    user.comments = []
    user.friends = []

    user.coins   = 500
    user.points  = 0

    user.switch_db("users")
    user.save()
    return user

def user_register(request):
    email = request.form['email']
    username = request.form['username']

    # generate password hash
    password_hash = flask_bcrypt.generate_password_hash(
        request.form['password'])
    try:
        user = create_user(email, username, password_hash)

        if login_user(user, remember="no"):
            session["user_id"] = username
            flash("Logged in!")
            return redirect(url_for("auth_app.profile"))
        else:
            flash("Unable to log you in")
    except:
        flash("Unable to register with that email address")
        current_app.logger.error("Error on registration - "
            "possible duplicate emails")

def user_login(request):
    username = request.form["username"]
    user = person_with_username(username)
    if user and user.is_active() and flask_bcrypt.\
        check_password_hash(user.password_hash, request.form["password"]):
        remember = request.form.get("remember", "no") == "yes"

        if login_user(user, remember=remember):
            session["user_id"] = username
            flash("Logged In!")

            identity_changed.send(current_app._get_current_object(),
                                  identity = Identity(user.id))
            return redirect(url_for("auth_app.profile"))
        else:
            flash("Unable to log you in")

class RegisterLoginView(View):
    def get_context(self):
        context = {
            "registration_form" : RegisterForm(),
            "login_form"        : LoginForm()
        }
        return context

    def get(self):
        """ Returns the index page when accessing home """
        context = self.get_context()
        registration_form = context.get("registration_form")
        login_form        = context.get("login_form")

        # case where already did login
        if g.user is not None and g.user.is_authenticated:
            return redirect(url_for("auth_app.profile")) 

        return render_template("index.html",
            registration_form=registration_form, login_form=login_form)

    def post(self):
        context = self.get_context()
        registration_form = context.get("registration_form")

        if "confirm" in request.form:
            if registration_form.validate():
                user_register(request)
                return redirect(url_for("auth_app.profile"))
            else: return "Registration Error" 

        # case where submitted a login request
        user_login(request)
        return redirect(url_for("auth_app.profile"))

    def dispatch_request(self):
        if request.method.lower() == 'get':
            return self.get()
        elif request.method.lower() == 'post':
            return self.post()
        return "Improper method used: {}".format(request.method)
    
def generate_password_reset_link(user_id):
    """ Returns a link for resetting the password of the account
    associated with DB object with user_id ID value

    Keyword arguments:
    user_id (string) -- ID of the account being resetted
    """

    # Clear out all old requests for this member
    for r in PasswordResetRequest.objects(user_id=user_id):
        session.pop(r.user_id, None)

    # Generate new password reset request
    reset_code = str(uuid4())
    reset_code_hash = flask_bcrypt.generate_password_hash(reset_code)
    reset_request = PasswordResetRequest(reset_code_hash=reset_code_hash,
        user_id=user_id, timestamp=datetime.now())
    reset_request.save()

    session.update({user_id : reset_code})

    # Return the reset password link
    return url_for('auth_app.reset_password', _external=True,
        id=reset_request.id, reset_code=reset_code)

@async
def send_async_email(message):
    """ Asynchronously sends the given message to a previously
    established connection (used in resetting passwords)

    Keyword arguments:
    message (string) -- Body/text for the e-mail
    """

    with mail.connect() as conn:
        with app.app_context():
            conn.send(message)

def send_email(subject, sender, recipients, text_body, html_body):
    """  Sends email with the given 

    Keyword arguments:
    message (string) -- Body/text for the e-mail
    """

    message = Message(subject, sender=sender, recipients=recipients)
    message.body = text_body
    message.html = html_body
    mail.send(message)

class ForgotView(View):
    def get_context(self):
        context = {
            "forgot_form" : ForgotForm()
        }
        return context

    def get(self):
        context = self.get_context()
        forgot_form = context.get("forgot_form")
        return render_template('forms/forgot.html', form=forgot_form) 

    def post(self):
        if "username" in request.form:
            user = person_with_username(request.form["username"])
            if user:
                reset_link = generate_password_reset_link(str(user.id))
                subject = "Plytos Password Reset"
                recipients = [user.email]
                body = ("Hello {name}! We received a password reset request "
                        "from you. If you did not make this request, please "
                        "ignore this email.\n"
                        "\n"
                        "You can reset your password using this link:\n"
                        "{reset_link}\n"
                        "\n"
                        "Thank you,\n"
                        "\n"
                        "Plytos Team"
                        ).format(name="placeholder", reset_link=reset_link)
                
                send_email(subject=subject,
                           sender="team@plytos.com",
                           recipients=recipients,
                           text_body=body,
                           html_body=None)
                
                flash("Request has been sent! Check your email for a link "
                      "to reset your password.", "success")
                return render_template('forms/forgot.html', form=forgot_form)

            else:
                flash("Email not found", "danger") 
        return render_template('forms/forgot.html', form=forgot_form)

    def dispatch_request(self):
        if request.method.lower() == 'get':
            return self.get()
        elif request.method.lower() == 'post':
            return self.post()
        return "Improper method used: {}".format(request.method)

class ResetView(View):
    def get_context(self):
        context = {
            "reset_form" : ResetPassForm()
        }
        return context

    def get(self):
        context = self.get_context()
        reset_form = context.get("reset_form")

        reset_request_id = request.args.get('id')
        reset_code = request.args.get('reset_code')

        reset_request = PasswordResetRequest.objects.get_or_404(
            id=reset_request_id)

        if not reset_request:
            flash("You do not have access to that page.", "danger")
            return render_template("index.html")

        if not reset_request.validate_reset_code(reset_code):
            flash("You do not have access to that page", "danger")
            return render_template("index.html")

        if not reset_request.validate_timestamp():
            flash("Password reset has expired", "danger")
            return render_template("index.html")
        return render_template('forms/reset_password.html', form=reset_form) 

    def post(self):
        context = self.get_context()
        reset_form = context.get("reset_form")

        password = request.form.get('password').strip()
        confirm = request.form.get('confirm').strip()

        has_errors = False
        if len(password) < MIN_PASSWORD_LENGTH:
            flash("Password must be at least {0} "
                  "characters".format(MIN_PASSWORD_LENGTH), "danger")
            has_errors = True
        if password != confirm:
            flash("Password and confirmation do not match", "danger")
            has_errors = True

        if not has_errors:
            user = person_with_username(g.user.username)
            password_hash = flask_bcrypt.generate_password_hash(password)
            try:
                user.reset_password(reset_request.user_id, password_hash)
                reset_request.delete()
                session.pop(reset_request.user_id, None)
                flash("You have successfully reset your password!", "success")
                return redirect(url_for('auth_app.home'))
            except:
                flash("Unable to reset password", "danger")
                current_app.logger.error("Error on registration - "
                    "possible duplicate emails") 
        return render_template('forms/reset_password.html', form=reset_form)

    def dispatch_request(self):
        if request.method.lower() == 'get':
            return self.get()
        elif request.method.lower() == 'post':
            return self.post()
        return "Improper method used: {}".format(request.method)

class LogoutView(View):
    def get(self):
        logout_user()
        for key in ('identity.name', 'identity.auth_type'):
            session.pop(key, None)
        identity_changed.send(current_app._get_current_object(),
                              identity=AnonymousIdentity())
        flash("Logged out.")
        return redirect(url_for("auth_app.home"))

    def dispatch_request(self):
        if request.method.lower() == 'get':
            return self.get()
        return "Improper method used: {}".format(request.method)

class ProfileView(View):
    def get_context(self):
        user = person_with_username(g.user.username)

        context = {
            "basic_form": BasicForm(obj=user.personal),
            "location_form": LocationForm(),
            "social_profile_form": SocialProfileForm()
        }
        return context

    def get(self):
        context = self.get_context()
        user = person_with_username(g.user.username)

        if user.personal is not None:
            self.locations       = user.personal.location
            self.social_profiles = user.personal.profiles

        basic_form = context.get('basic_form')
        location_form = context.get('location_form')
        social_profile_form = context.get('social_profile_form')

        return render_template("forms/profile.html", user=user,
            basic_form=basic_form, 
            location_form=location_form, 
            social_profile_form=social_profile_form)

    def post(self):
        context = self.get_context()
        user = person_with_username(g.user.username)

        basic_form = context.get('basic_form')
        location_form = context.get('location_form')
        social_profile_form = context.get('social_profile_form')

        if user.personal is None:
            personal_info           = Personal()
            personal_info._id       = ObjectId()
            user.personal           = personal_info

        if "submit" in request.form and "Location" in request.form["submit"]\
            and location_form.validate():

            new_location           = Location()
            new_location._id       = ObjectId()
            location_form.populate_obj(new_location)
            user.personal.location.append(new_location)

        elif "submit" in request.form and "Profile" in request.form["submit"]\
            and social_profile_form.validate():
            
            new_social              = SocialMediaItem()
            new_social._id          = ObjectId()
            social_profile_form.populate_obj(new_social)
            user.personal.profiles.append(new_social)

        elif basic_form.validate():
            basic_form.populate_obj(user.personal)

        user.switch_db("users")
        user.save()
        
        return redirect(url_for('auth_app.profile'))

    def dispatch_request(self):
        if request.method.lower() == 'get':
            return self.get()
        elif request.method.lower() == 'post':
            return self.post()
        return "Improper method used: {}".format(request.method)

def setup_auth(auth_app):
    auth_app.add_url_rule('/', view_func=RegisterLoginView.as_view('home'), 
        methods=['GET', 'POST'])
    auth_app.add_url_rule('/profile', view_func=ProfileView.as_view('profile'), 
        methods=['GET', 'POST'])
    auth_app.add_url_rule('/logout', view_func=LogoutView.as_view('logout'), 
        methods=['GET'])
    auth_app.add_url_rule('/reset_password', 
        view_func=ResetView.as_view('reset_password'), methods=['GET', 'POST'])
    auth_app.add_url_rule('/forgot', view_func=ForgotView.as_view('forgot'), 
        methods=['GET', 'POST'])

auth_app = Blueprint('auth_app', __name__, template_folder='templates')
setup_auth(auth_app)