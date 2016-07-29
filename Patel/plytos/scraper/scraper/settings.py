# Scrapy settings for craigslist_jobs project
#
# For simplicity, this file contains only the most important settings by
# default. All the other settings are documented here:
#
#     http://doc.scrapy.org/en/latest/topics/settings.html
#

BOT_NAME = 'scraper'
SPIDER_MODULES = ['scraper.spiders']
NEWSPIDER_MODULE = 'scraper.spiders'

# Crawl responsibly by identifying yourself (and your website) on the user-agent
DEPTH_LIMIT = 50

MEMUSAGE_REPORT = True

AJAXCRAWL_ENABLED = True
COOKIES_ENABLED = False
DOWNLOAD_DELAY = 2

LOG_ENABLED = True

############### MongoDB Settings #####################
# ITEM_PIPELINES = {
#     'scraper.pipeline.MongoDBPipeline': 0, 
# }
#         
# MONGODB_SERVER = "localhost"
# MONGODB_PORT = 27017
# MONGODB_DB = "plytos"
# MONGODB_COLLECTION = "resumes"