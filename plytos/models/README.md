Models
======
Serves as the "Models" segment of the MVC (Model-View-Controller) web architecture.
Included are models for the following:
	- Comments
	- Jobs
	- Person
	- Reset
	- Resume

Comments
--------
Comment object for each section that is editable by users. These objects allow people
who are forking other users' resumes to not only make direct edits, but suggest where
they should concentrate their efforts for future iterations. 

Jobs
--------
Listings for the jobs available for users to apply to. These jobs will be free streaming
from external sources and are the endpoint for the proprietary career-pathing algorithm

Person
--------
User objects for people who register for the website. These users have their personal
information along with connections to each of the other objects (can select jobs, leave
comments, make reset requests for their account, and own/edit resumes).

Reset
--------
Reset requests simply serve on the back-end to allow people to reset passwords -- no
external/explicit instance should occur aside from this

Resume
--------
The central object around which the application revolves, this resume has pre-defined
fields, allowing for well-defined collaboration and iterative progression