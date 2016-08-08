Technology Overview
==================
Application Server
------------------
Description: Used primarily to handle all the requests by the 
client to serve files and do any pre-processing or on-the-fly
analytics in the request (i.e. for determining content). The
app server typically has an embedded web server in the form of
Apache or the like.

I would recommend switching over to Django once we move from development phase 
to production, as it seems much safer/robust to maintain.

    - Flask (current): Micro-framework that we are currently using -- it works
        quite well for us, as it is easy to use and maintain. However,
        due to its rather flexible structure, it may become hard to maintain
        as the code goes into production-level. 

    - Django (recommended): Very heavy-weight production-level framework. It
        comes with much of the plumbing set up and ready to use. There's no
        point wasting time now (for developing the MVP) switching over to
        Django, since there are much more pressing matters at hand. 

Django comes readied for being deployed as a production-level application
server (I believe). Flask, which we'll stick with for now, however, does not
(http://flask.pocoo.org/docs/0.11/deploying/). Flask requires a separate 
WSGI server, as specified in the below section.

Web Server
------------------
Description: Largely the "lowest-level" server, the web server
handles the connection of clients to sockets on the server and
also determines how to handle asynchronous (multiple) connections. We
need to use this in the case of our Flask server (or could deploy to
a hosting site, such as Heroku/Amazon). Doesn't seem like any work
at all (just use a different command-line command)

    - Twisted (recommended): An asynchronous library that we we'll use for deploying 
        the Flask code. Simply use twistd web --wsgi myproject.app for running 
        the code with Twisted.

Databases
------------------
Description: Where all the persistent data is maintained, both
used for the data that is directly transparent to users (i.e. 
the actual resumes and users) or not (i.e. the test data being
scraped for development purposes)

    - MongoDB (current): A NoSQL DB we're using for storing all the data
        that is accessible by users. We have three (3) separate collections:
            - User: Clients that have registered for the service 
            - Resumes: Documents saved for the clients
            - Jobs: Listings that are accessible by the clients

        These three are related in the following manner:
            - User/Resumes:
                - Users have many of their own (personal) resumes
                - Users can edit any number of other people's resumes
                - Resumes have exactly one creator
            - User/Jobs: 
                - Users can pursue/add jobs they are interested in
            - Resume/Jobs: 
                - Resumes of a user will be used to determine relevant jobs
                    (No direct relation between these)

    - Redis (current): A key-value DB -- ONLY used in development.
        This feature will be entirely eliminated during production, since 
        the main purpose of this DB is to collect a training corpus for
        the career pathing algorithm (i.e. creating the word2vec vector
        space). Once the space is created and the w2v algo trained, this
        DB will be deprecated -- any additional training.


Data Analytics
------------------
Description: Used primarily for development/training -- this will
NOT be accessed/run when requests are made by the user. After the
code goes into production, these technologies will not be in active
use (compared to the above)

    - Hadoop (recommended): As with the Redis DB, this will be used for
        developing the training corpus and career pathing tool. Hadoop will
        primarily be used to process computationally-intensive work
        (i.e. generating n-grams, w2v training(??), etc...). Once this segment
        is done, no Hadoop processes will run (i.e. while clients are
        using the service), as response times would be inordinately slow

Technology Interface
====================
With that behind, the following is how these technologies interface:

Development
------------------
App-Server: Flask
Web-Server: Twisted (interface Flask)
DB: MongoDB (interface w/ Flask)
    Redis -- train w2v and use on back-end (serve results via Flask)
Hadoop: Train w2v

Production
------------------
App-Server: Django -- already have w2v trained and usable
Web-Server: Twisted (through Django)
DB: Mongo (interface w/ Django)

Path to Deployment
==================
With that, here is the path I believe we should take to get to the MVP
and how we should progress from there:

MVP Path
------------------
We'll implement all the technologies that were mentioned under the
development heading. Specifically, we want to mainly want to show the 
product at this point in a non-technical sense, i.e. without
exposing the underlying code. This means it may usually be better to
have a quick hack rather than spending too much time being
held up on minor issues. Of course, it's always preferable to have
the final production-level code readied so the transition to the next
phase is as smooth as possible. At this point, little to no regard
should be placed on the UI/UX.

Most of the work on the app-server has been completed. We will make
this into a fully-functional web-server by running with Twisted. Thus,
there isn't much work that has to be done with the application itself
from an MVP standpoint (discussion of changes for production are in the
section below). We should focus most attention on developing the
career pathing algorithm/code, since that's pivotal for the MVP and
requires thought. After the algorithm's developed, the only addition
necessary is actually obtaining the job listings and applying the algo
to show it's output in action.

Production Path
------------------
At this point, we should have the following: A Flask-based web application,
fully functional with a NoSQL Mongo DB that is capable of authenticating
users, allowing them to do edits/revisions (through explicit registration),
and find jobs via a custom career-pathing algorithm, whose output is the 
result of a w2v algo trained on a custom corpus, produced as a result of
Hadoop. We, therefore, should have not much further need for the Hadoop
and Redis, as the w2v algo has been trained (unless retraining is
desired, in which case we can simply boot these two up again).

We must now switch from the Flask application to a production-level Django
app. The UI/UX will now be a large concern for development (i.e. the
user should NOT have to input the exact ID of the resume they wish to edit).