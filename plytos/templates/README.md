Templates
=============
Serves all the dynamic HTML pages, i.e. those whose values are altered by Flask. Many
of such pages include some form of jinja2 templating. These templates are broken
into the following sections:
- Errors
- Forms
- Jobs
- Layouts
- Profile
- Resumes
- Misc

Errors
--------------
Pages that are rendered when any error is encountered on the website. This could include
an invalid request (i.e. incorrect URL) or if something breaks on server-side (physically
or crash in software), making user experience less disruptive.

Forms
--------------
Page for rendering all the forms that were available for the user to fill out and either
create their account information or objects associated with it

Jobs
--------------
Page where jobs are streamed and can be viewed by interested users

Layouts
--------------
Basic template used for all the main and forms pages (i.e. serves as a layout over
which fields are transcribed)

Profile
--------------
Social/user profile visible publicly for others to access and receieve resume info.

Resumes
--------------
All pages associated with viewing, editing, creating, reviewing, and finalizing a 
user's own and editing documents

Misc
--------------
Miscellaneous files that are included as sub-parts of other pages' content