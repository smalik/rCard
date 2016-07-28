"""
run.py: Module-level executable file. Used to run the Flask
server application in the production folder (./Plytos)

__author__ = "Yash Patel"
__copyright__ = "Copyright 2016, Plytos Inc."

__license__ = "Free/Open"
__version__ = "1.0.0"
__maintainer__ = "Yash Patel"
__email__ = "ypatel@princeton.edu"
"""

from plytos import app

if __name__ == "__main__":
	app.run(host="0.0.0.0", port=9000)