"""
pipelines.py: Creates the pipeline for feeding the scraped data
into the relevant MongoDB database. Used for populating the
test/development-level DB

__author__ = "Yash Patel"
__copyright__ = "Copyright 2016, Plytos Inc."

__license__ = "Free/Open"
__version__ = "1.0.0"
__maintainer__ = "Yash Patel"
__email__ = "ypatel@princeton.edu"
"""

import pymongo
from scrapy.conf import settings
from scrapy.exceptions import DropItem

class MongoDBPipeline(object):
    """  Pipeline for streaming scrape result to Mongo DB """

    def __init__(self):
        """ Initializes connection to Mongo DB """

        connection = pymongo.MongoClient(
            settings['MONGODB_SERVER'],
            settings['MONGODB_PORT']
        )
        db = connection[settings['MONGODB_DB']]
        self.collection = db[settings['MONGODB_COLLECTION']]

    def process_item(self, item, spider):
        """ Saves the specified item to the configured Mongo DB

        Keyword arguments:
        item -- Item being stored to the DB
        spider -- Spider that scraped the object being saved
        """

        valid = True
        for data in item:
            if not data:
                valid = False
                raise DropItem("Missing {0}!".format(data))
        if valid:
            self.collection.insert(dict(item))
        return item