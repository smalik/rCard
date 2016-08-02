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
DEFAULT_REQUEST_HEADERS = {
    'referer': 'http://www.google.com'
}

USER_AGENT = "Mozilla/5.0 (Windows NT 6.2; WOW64) Chrome/27.0.1453.93 Safari/537.36"

############### MongoDB Settings #####################
ITEM_PIPELINES = {'scraper.pipelines.MongoDBPipeline': 0,}

MONGODB_SERVER = "localhost"
MONGODB_PORT = 27017
MONGODB_DB = "resume"
MONGODB_COLLECTION = "resume"