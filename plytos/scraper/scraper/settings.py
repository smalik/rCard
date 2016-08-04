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

DOWNLOADER_MIDDLEWARES = {
        'scrapy.contrib.downloadermiddleware.useragent.UserAgentMiddleware' : None,
        'scraper.rotate_useragent.RotateUserAgentMiddleware' :200,
        'scrapy_crawlera.CrawleraMiddleware': 300
}

CRAWLERA_ENABLED = True
CRAWLERA_APIKEY = 'b9d2ed74df214e97bf3e5d0765990554'

CONCURRENT_REQUESTS = 51
CONCURRENT_REQUESTS_PER_DOMAIN = 51
AUTOTHROTTLE_ENABLED = False
DOWNLOAD_TIMEOUT = 300


DEPTH_LIMIT = 1
MEMUSAGE_REPORT = True

AJAXCRAWL_ENABLED = True
COOKIES_ENABLED = False
DOWNLOAD_DELAY = 5

LOG_ENABLED = True

# USER_AGENT = "Mozilla/5.0 (Windows NT 6.2; WOW64) Chrome/27.0.1453.93 Safari/537.36"

############### MongoDB Settings #####################
ITEM_PIPELINES = {'scraper.pipelines.MongoDBPipeline': 0,}

MONGODB_SERVER = "localhost"
MONGODB_PORT = 27017
MONGODB_DB = "resume"
MONGODB_COLLECTION = "resume"
