Plytos
======

Open source plytos, a flask app for job search and collaboration. The primary technologies used are:

Python 3.5+
Flask
Jinja and WTForms
MongoDB and MongoEngine
JavaScript, JQuery, Leaflet.js
Bootstrap 3, Font Awesome

# rCard

Usage
=======
The basic functionality revolves around being able to create resumes and for other people
to "fork" off these resumes in a git-like fashion, allowing them to make revisions and
push back to the original user for approval. Currently, the system is set up with 8 main tabs
of functionality, each explained more thoroughly below:

- Authentication
	- Login
	- Register
	- Logout

- Self-Management
	- View
	- Create

- Forked-Management
	- Find
	- Edit

- Review
- Finalized

Authentication
==============
These are the blue tabs, which are used to set up the user and take care of the basic
logistics involved in almost any standard web application

Login
--------------
Standard login procedure: enter your username and password where prompted. If you are
logging in, it must be the case that (at some point in the past), you registered that
identical pair through the Register panel, i.e. logging in with new credentials does not
automatically create a new account. If you are already logged in and attempt to access
this tab, it will redirect you to the home page.

Register
--------------
As mentioned in the login description, this is where you sign up for new accounts. No
verification is performed on the email address, so invalid ones may too be used for
registration at this point. Once you register an account, you will be automatically
logged in with that account and redirected to the home page. If you are logged in and
attempt to access this page, it will redirect you to the home page.

Logout
--------------
Logs out the current session of the user, after logging in or registration has occurred.
If attempted to perform when not logged in, simply redirects to the home page.


Self-Management -- Login Required
==============
View
--------------
Fetches all the resumes that are linked to the account of the user logged in. Lists all
these in a format with the Name (unique Resume ID), Skills, Experience, and Education
along with all comments (explained in "Forked-Management" section below).

Note: The resume ID is used quite often for interactions and should (at a later point in
which UI becomes more critical) be removed from explicit use by the users.

Create
--------------
Tab where the user can make a new personal resume. There are five sections of the resume:
	- Work
	- Volunteer
	- Education
	- Awards
	- Overall/Misc.

Each of the first four (i.e. work, volunteer, education, awards) may contain several
separate instances. For example, you may have many previous jobs, which would each be 
"1 work" instance. So, for creating any of these, you fill in the appropriate fields
(separated by horizontal rules) and press the "Create New" at the bottom. Note that
pressing Save (at the very bottom) does NOT save any current/partially-completed
instances. After pressing "Create New," the page should refresh and all the fields
will now be empty. 

Also, for these four cumulative fields fields (to avoid clutter), any values that
need to be filled out that are plural (i.e. Highlights, Skills) should be filled out
with individual instances separated by commas.

The Overall/Misc fields only have one instance for the entire resume. After filling out
all the appropriate/desired fields, press "Save" at the bottom. This should add it to
the view page from above.


Forked-Management -- Login Required
==============
Find -- External ID Required
--------------
This is where all external forks are added. Enter in a valid ID and press Submit to add
it to your list of "Editing" documents. Note: Entering an invalid ID of a resume will
cause a 404 to be thrown. Additional Note: Entering in an ID of one of your resumes is
considered perfectly valid in the current implementation, which may or may not be 
desired going forward.

Edit
--------------
Similar to the "View" page, this is where all the documents being edited are placed.
Press the edit link that is under the document you wish to edit. All the panels are
organized as they were in the "Create" view, with the exception of this having lists
of the "cumulative fields" rather than explicitly putting them on the first page. So,
to edit these, click on the appropriate link, and do the editing that spot. Pressing
"Save" on those individual pages will redirect you to the original resume-edit screen.

After completing all the desired revisions, press Save to save the revisions locally.
You MUST save prior to pushing to capture any saves you make to the overall-resume
fields (i.e. publications/interests) -- the cumulative fields will save when you
save on their appropriate page. Once all editing is complete, you may press push to
push it up to the original user's account. 

In addition to revisions, you can edit, both on the overall document and on the 
cumulative-list fields. Upon pressing "Comment," the comment will be saved and updated
on the original user's account.


Review -- Login Required
==============
After an external user has done their revisions and pushed their changes, the changes
will be visible in your account under the "Review" tab. This tab contains a list of
all the changes that occurred (numbered) along with a "Publish" option. Upon 
clicking one of the changes, you will be able to select what fields you wish to Accept
and Reject. Reject currently has no functionality, aside from redirecting you to the
original list view, while accept automatically changes the contents of the resume,
which is reflected on the "View" tab.

After making all the desired changes, you can "Publish" the document, whereby you 
delete the entire edit history and make the document public.


Finalized -- Login Required
==============
After you publish a document, this screen (identical to the "View" tab) is where it
is populated. You should only be able to see documents you published here.
