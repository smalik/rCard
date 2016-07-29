# Define here the models for your scraped items
#
# See documentation in:
# http://doc.scrapy.org/en/latest/topics/items.html

from scrapy.item import Item, Field

# Captures the structures of each of the following classes:
# - Volunteer
# - Education
# - Awards
# - Publications
class ItemList(object):
    def __init__(self):
        self.items = []
        self.comments = []
    
    def encode(self, obj):
        return obj.__dict__

class VolunteerItem(Item):
    org           = Field()
    title         = Field()
    startDt       = Field()
    endDt         = Field()
    url           = Field()
    impact        = Field()

    highlights    = Field()

    def encode(self, obj):
        return obj.__dict__

class WorkItem(Item):
    position         = Field()
    company          = Field()
    start_date       = Field()
    end_date         = Field()
    description      = Field()

    url              = Field()
    highlights       = Field()
    skills           = Field()

    def encode(self, obj):
        return obj.__dict__

class SchoolItem(Item):
    school          = Field()
    degree          = Field()
    locale          = Field()
    admit_date      = Field()
    grad_date       = Field()

    gpa          = Field()
    courses      = Field()

    def encode(self, obj):
        return obj.__dict__


class AwardItem(Item):
    title        = Field()
    date         = Field()
    issuer       = Field()
    desc         = Field()
    url          = Field()

    def encode(self, obj):
        return obj.__dict__

class ResumeItem(Item):
    parent_user   = Field()
    skills        = Field()

    experience    = Field()
    volunteer     = Field()
    education     = Field()
    awards        = Field()

class ResumeDataItem(Item):
    # define the fields for your resume here:
    name        = Field()
    url         = Field()
    email       = Field()
    phone       = Field()
    headline    = Field()
    locale      = Field()
    summary     = Field()
    experience  = Field()
    education   = Field()    
    skills      = Field()
    links       = Field()

    def getName(self):
        return self.name
    
    def encode(self, obj):
        return obj.__dict__