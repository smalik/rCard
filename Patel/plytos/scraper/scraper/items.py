"""
items.py: Models for the scraping process -- equivalent to those
used in the models of the overall production to make this relevant
for testing development code

__author__ = "Yash Patel"
__copyright__ = "Copyright 2016, Plytos Inc."

__license__ = "Free/Open"
__version__ = "1.0.0"
__maintainer__ = "Yash Patel"
__email__ = "ypatel@princeton.edu"
"""

from scrapy.item import Item, Field

# Each item has set of values that are not available from 
# indeed.com scraping -- just set these variables to default

# Captures the structures of each of the following classes:
# - Volunteer
# - Education
# - Awards
# - Publications
class ItemList(Item):
    _id           = Field()

    items         = Field()
    comments      = Field()
    
    def encode(self, obj):
        return obj.__dict__

class WorkItem(Item):
    _id           = Field()

    position         = Field()
    company          = Field()
    start_date       = Field()
    end_date         = Field()
    description      = Field()

    ###################### DEFAULT ##########################
    url              = Field()
    highlights       = Field()
    skills           = Field()

    def encode(self, obj):
        return obj.__dict__

class SchoolItem(Item):
    _id           = Field()

    school          = Field()
    degree          = Field()
    locale          = Field()
    admit_date      = Field()
    grad_date       = Field()

    ###################### DEFAULT ##########################
    gpa             = Field()
    courses         = Field()

    def encode(self, obj):
        return obj.__dict__


class ResumeItem(Item):
    _id           = Field()

    parent_user   = Field()
    skills        = Field()

    experience    = Field()
    volunteer     = Field()
    education     = Field()
    awards        = Field()

    ###################### DEFAULT ##########################
    skills               = Field()
    pubs                 = Field()
    interests            = Field()
    languages            = Field()
    comments_per_section = Field()
    todos_per_section    = Field()
    
    comments             = Field()
    version              = Field()
    num_edits            = Field()
    editDt               = Field()
    slug                 = Field()