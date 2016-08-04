# Scrapy settings for simplyspider project
#
# For simplicity, this file contains only the most important settings by
# default. All the other settings are documented here:
#
#     http://doc.scrapy.org/en/latest/topics/settings.html
#

BOT_NAME = 'simplyspider'

SPIDER_MODULES = ['simplyspider.spiders']
NEWSPIDER_MODULE = 'simplyspider.spiders'

DOWNLOADER_MIDDLEWARES = {
        'scrapy.contrib.downloadermiddleware.useragent.UserAgentMiddleware' : None,
        'simplyspider.rotate_useragent.RotateUserAgentMiddleware' :200
}


# Crawl responsibly by identifying yourself (and your website) on the user-agent
#USER_AGENT = 'simplyspider (+http://www.yourdomain.com)'

ITEM_PIPELINES = {
    'simplyspider.pipelines.SimplyspiderPipeline' : 100
}
DUPEFILTER_CLASS = 'scrapy.dupefilter.BaseDupeFilter'

DEPTH_LIMIT = 100

MEMUSAGE_REPORT = True

AJAXCRAWL_ENABLED = True
COOKIES_ENABLED = False
DOWNLOAD_DELAY = 5

LOG_ENABLED = True
