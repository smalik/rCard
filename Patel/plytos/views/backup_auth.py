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
from flask.ext.login import (login_user, 
    logout_user, confirm_login, current_user)
from flask.ext.principal import Identity, AnonymousIdentity, identity_changed
from flask.ext.mail import Message

from uuid import uuid4
from datetime import datetime

from plytos import login_manager, flask_bcrypt, mail, app
from plytos.decorators import async, login_required
from plytos.libs.User import User

from plytos.models.comments import Comment
from plytos.models.reset import PasswordResetRequest
from plytos.forms import LoginForm, RegisterForm, ForgotForm, ResetPassForm

MIN_PASSWORD_LENGTH = 4
auth_login = Blueprint('auth_login', __name__, template_folder='templates')

# General Request Handlers
@app.before_request
def before_request():
    if "user_id" in session and session["user_id"]:
        userObj = User()
        g.user = userObj.get_by_username(session["user_id"])
    else:
        g.user = current_user
    
@app.route('/')
def home():
    return render_template("index.html")

@auth_login.route('/register', methods=["GET", "POST"])
def register():
    form = RegisterForm()
    # current_app.logger.info(request.form)
    if g.user is not None and g.user.is_authenticated:
        return redirect(url_for("resume_app.list"))

    if request.method == "POST" and form.validate() == False:
        current_app.logger.info(form.errors)
        return "Registration Error"

    elif request.method == "POST" and form.validate():
        email = request.form['email']
        username = request.form['username']

        # generate password hash
        password_hash = flask_bcrypt.generate_password_hash(
            request.form['password'])
        
        user = User(
            email = email,
            password_hash = password_hash, 
            active = True, 
            username = username
        )
        try:
            user.save()
            if login_user(user, remember="no"):
                session["user_id"] = username
                flash("Logged in!")
                return redirect(url_for("resume_app.list"))
            else:
                flash("Unable to log you in")
        except:
            flash("Unable to register with that email address")
            current_app.logger.error("Error on registration - "
                "possible duplicate emails")

    return render_template('forms/register.html', form=form)

@auth_login.route('/login', methods=["GET", "POST"])
def login():
    form = LoginForm()
    if g.user is not None and g.user.is_authenticated:
        return redirect(url_for("resume_app.list"))

    if request.method == "POST" and "username" in request.form:
        username = request.form["username"]
        userObj = User()
        user = userObj.get_by_username(username)
        if user and user.is_active() and flask_bcrypt.\
            check_password_hash(user.password_hash, request.form["password"]):
            remember = request.form.get("remember", "no") == "yes"

            if login_user(user, remember=remember):
                session["user_id"] = username
                flash("Logged In!")

                identity_changed.send(current_app._get_current_object(),
                                      identity = Identity(user.id))
                return redirect(url_for("resume_app.list"))
            else:
                flash("Unable to log you in")
    return render_template('forms/login.html', form=form)

def generate_password_reset_link(user_id):
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
    return url_for('auth_login.reset_password', _external=True,
        id=reset_request.id, reset_code=reset_code)

@async
def send_async_email(message):
    with mail.connect() as conn:
        with app.app_context():
            conn.send(message)

def send_email(subject, sender, recipients, text_body, html_body):
    message = Message(subject, sender=sender, recipients=recipients)
    message.body = text_body
    message.html = html_body
    mail.send(message)
    # send_async_email(message)

@auth_login.route('/forgot', methods=["GET", "POST"])
def forgot():
    form = ForgotForm()
    if request.method == "POST" and "username" in request.form:
        username = request.form["username"]
        userObj = User()
        user = userObj.get_by_username(username)

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
            return render_template('forms/forgot.html', form=form)

        else:
            flash("Email not found", "danger")
    return render_template('forms/forgot.html', form=form)


@auth_login.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    form = ResetPassForm()
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

    if request.method == "POST":
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
            userObj = User()
            password_hash = flask_bcrypt.generate_password_hash(password)
            try:
                userObj.reset_password(reset_request.user_id, password_hash)
                reset_request.delete()
                session.pop(reset_request.user_id, None)
                flash("You have successfully reset your password!", "success")
                return redirect(url_for('auth_login.login'))
            except:
                flash("Unable to reset password", "danger")
                current_app.logger.error("Error on registration - "
                    "possible duplicate emails")               

    return render_template('forms/reset_password.html', form=form)

@auth_login.route("/logout")
@login_required
def logout():
    logout_user()
    for key in ('identity.name', 'identity.auth_type'):
        session.pop(key, None)
    identity_changed.send(current_app._get_current_object(),
                          identity=AnonymousIdentity())
    flash("Logged out.")
    return redirect(request.args.get('next') or '/')

@auth_login.route('/<username>/')
@login_required
def profile(username):
    userObj = User()
    user = userObj.get_by_username(username)

    if user == None:
        flash('User ' + username + ' not found.')
        return render_template("index.html")

    #FIXME: just mock data
    posts = [
        { 'author': user, 'body': 'Test post #1' },
        { 'author': user, 'body': 'Test post #2' }
    ]
    return render_template('profile/user.html',
        user = user,
        posts = posts)

@login_manager.unauthorized_handler
def unauthorized_callback():
    flash('Please login', 'warning')
    return redirect('/login?next=' + request.path)

@login_manager.user_loader
def load_user(uname):
    if uname is None:
        redirect('/login')
    user = User()
    user.get_by_username(uname)
    if user.is_active():
        return user
    else:
        return None