Scraper
============
Scrapy web-scraper for Indeed.com. This scrapy spider can be run with:

	scrapy crawl resume

The intended result is that all URLs specified in the given file will be
read/scraped and used to populate the back-end MongoDB, from which further
transformations can be used to make a training corpus for word2vec.