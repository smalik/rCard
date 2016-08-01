"""
settings.py: Parameters used to instantiate the scraper --
also specifies the DB to which the results are saved

__author__ = "Yash Patel"
__copyright__ = "Copyright 2016, Plytos Inc."

__license__ = "Free/Open"
__version__ = "1.0.0"
__maintainer__ = "Yash Patel"
__email__ = "ypatel@princeton.edu"
"""

BOT_NAME = 'scraper'
SPIDER_MODULES = ['scraper.spiders']
NEWSPIDER_MODULE = 'scraper.spiders'

DEPTH_LIMIT = 50

MEMUSAGE_REPORT = True

AJAXCRAWL_ENABLED = True
COOKIES_ENABLED = False
DOWNLOAD_DELAY = 2

LOG_ENABLED = True

############### MongoDB Settings #####################
ITEM_PIPELINES = {'scraper.pipelines.MongoDBPipeline': 0,}

MONGODB_SERVER = "localhost"
MONGODB_PORT = 27017
MONGODB_DB = "resume"
MONGODB_COLLECTION = "resume"