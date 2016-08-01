"""
resume_spider.py: Spider object used to crawl around the Indeed
resume website and collect information/make resume objects for
saving to the development DB

__author__ = "Yash Patel"
__copyright__ = "Copyright 2016, Plytos Inc."

__license__ = "Free/Open"
__version__ = "1.0.0"
__maintainer__ = "Yash Patel"
__email__ = "ypatel@princeton.edu"
"""

#!/usr/bin/env python
import types
import time
from datetime import date, datetime, timedelta

import requests
import msgpack
from bson.objectid import ObjectId

from scrapy import Spider
from scrapy.shell import inspect_response
from scrapy.spiders import Rule
from scrapy.linkextractors import LinkExtractor
from scrapy.selector import Selector

from scraper.items import ResumeItem, WorkItem, SchoolItem, ItemList

import sys

class ResumeIndeedSpider(Spider):
    name = "resume"
    allowed_domains = ["indeed.com"]
    start_urls = ['http://www.indeed.com/resumes/statistics-python',]
                  #'http://www.indeed.com/resumes/statistics-python',
                  #'http://www.indeed.com/resumes/data-scientist',
                  #'http://www.indeed.com/resumes/python',]
                  #'http://www.indeed.com/resumes/java',
                  #'http://www.indeed.com/resumes/SAS',
                  #'http://www.indeed.com/resumes/javascript',
                  #'http://www.indeed.com/resumes/marketing-analyst',
                  #'http://www.indeed.com/resumes/biomedical',
                  #'http://www.indeed.com/resumes/physicist',
                  #'http://www.indeed.com/resumes/business-analyst',
                  #'http://www.indeed.com/resumes/writer',
                  #'http://www.indeed.com/resumes/product-manager',
                  #'http://www.indeed.com/resumes/produce-manager',
                  #'http://www.indeed.com/resumes/technical-writer',
                  #'http://www.indeed.com/resumes/photographer',
                  #'http://www.indeed.com/resumes/dev-ops',
                  #'http://www.indeed.com/resumes/architect',
                  #'http://www.indeed.com/resumes/civil-engineer',
                  #'http://www.indeed.com/resumes/graphic-designer',
                  #'http://www.indeed.com/resumes/electrical-engineer',
                  #'http://www.indeed.com/resumes/server',
                  #'http://www.indeed.com/resumes/translator',
                  #'http://www.indeed.com/resumes/animator']

    rules = (Rule(LinkExtractor(
        restrict_xpaths = ('//a[@class="instl confirm-nav next"]')), 
        callback = "parse_item", follow = True),)

    def parse(self, response):
        hxs     =   Selector(response)
        digest  =   hxs.xpath('//ol[@class="resultsList"]')
        
        url_prefix = 'http://www.indeed.com'

        resume_links   =   digest.xpath('//li[@class="sre"]//div[@class="sre-entry"]')
        names   =   digest.xpath('//a[@target="_blank"]/text()').extract()
        links   =   digest.xpath('//a[@target="_blank"]/@href').extract()
                
        count = 0
        for name, link in zip(names, links):
            if name not in 'Feedback':
                if "http://" not in link:
                    link =   url_prefix + link
                records = self.parse_node(requests.get(link))

                if records:
                    yield records

    def get_work(self, hxs):
        workHistory =   []
        experience  =   hxs.xpath('//div[@id="work-experience-items"]/div')
        for elem in experience:
            item = elem.xpath('div')
            for entry in item:
                workEntry   =   WorkItem()

                position       =   entry.xpath('p[@class="work_title title"]'
                    '//text()').extract()
                workEntry['position']  =   str(''.join(position))

                company     =   entry.xpath('div[@class="work_company"]'
                    '/span/text()').extract()
                workEntry['company']=   str(''.join(company))

                dates       =   entry.xpath('p[@class="work_dates"]//text()').extract()
                dates_str   =   str(''.join(dates)).split(' to ')
                if len(dates) > 0:
                    if dates_str[0]:
                        workEntry['start_date'] =   dates_str[0]
                    if dates_str[1]:
                        workEntry['end_date']   =   dates_str[1]
                else:
                    workEntry['start_date'] =   'NULL'
                    workEntry['end_date']   =   'NULL'
                    

                description =   entry.xpath('p[@class="work_description"]'
                    '//text()').extract()
                workEntry['description']    =   str(''.join(description))

                ################### DEFAULT #######################
                workEntry['_id']          = str(ObjectId())
                workEntry['url']          = ""
                workEntry['highlights']   = []
                workEntry['skills']       = []

                workHistory.append(workEntry.encode())
        return workHistory

    def get_edu(self, hxs):
        eduHistory =   []
        education  =   hxs.xpath('//div[@id="education-items" '
            'and @class="items-container"]/div')
        for elem in education:
            item = elem.xpath('div')
            for entry in item:
                eduEntry    =   SchoolItem()

                degree      =   entry.xpath('p[@class="edu_title"]'
                    '/text()').extract()
                degree      =   str(''.join(degree))
                eduEntry['degree']  =   degree

                school      =   entry.xpath('div[@class="edu_school"]'
                    '/span//text()').extract()
                school      =   str(''.join(school))
                eduEntry['school']  =   school

                locale      =   entry.xpath('span[@itemprop="addressLocality"]'
                    '/text()').extract()
                locale      =   str(''.join(locale))
                eduEntry['locale']  =   locale
                
                grad_date   =   entry.xpath('p[@class="edu_dates"]'
                    '/text()').extract()
                dates_str   =   str(''.join(grad_date)).split(' to ')
                if len(grad_date) > 0:
                    if len(dates_str) == 2:
                        if dates_str[0]:
                            eduEntry['admit_date']  =   dates_str[0]
                        try:
                            if dates_str[1]:
                                eduEntry['grad_date']   =   dates_str[1]
                        except:
                            pass
                    elif len(dates_str) == 1:
                        if dates_str[0]:
                            eduEntry['grad_date']  =   dates_str[0]
                            eduEntry['admit_date'] =   'NULL'
                else:
                    eduEntry['admit_date']  =   'NULL'
                    eduEntry['grad_date']   =   'NULL'

                ################### DEFAULT #######################
                eduEntry['_id']       = str(ObjectId())
                eduEntry['gpa']       = 0.0
                eduEntry['courses']   = []

                eduHistory.append(eduEntry.encode())
        return eduHistory

    def parse_node(self, response):
        hxs     =   Selector(response)
        name        =   hxs.xpath('//h1[@id="resume-contact"]/text()').extract()

        headline    =   hxs.xpath('//h2[@id="headline"]/text()').extract()

        rlocale      =   hxs.xpath('//p[@id="headline_location" '
            'and @class="locality"]//text()').extract()
        summary     =   hxs.xpath('//p[@id="res_summary" '
            'and @class="summary"]/text()').extract()
        skills      =   list()
        skill       =   hxs.xpath('//div[@id="skills-items" '
            'and @class="items-container"]//p//text()').extract()
        if len(skill) != 0:
            skills.append(str(''.join(skill)))        
        skill       =   hxs.xpath('//div[@id="additionalinfo-section" '
            'and @class="last"]//div[@class="data_display"]//p//text()').extract()
        if len(skill) != 0:
            skills.append(str(''.join(skill)))        
        
        resume_links    =   list()
        links       =   hxs.xpath('//div[@id="link-items" '
            'and @class="items-container"]//p//text()').extract()
        for link in links:
            resume_links.append(str(''.join(link)))

        workItemList = ItemList()
        workItemList['_id']      = str(ObjectId()) 
        workItemList['items']    = self.get_work(hxs)
        workItemList['comments'] = []

        eduItemList = ItemList()
        eduItemList['_id']      = str(ObjectId()) 
        eduItemList['items']    = self.get_edu(hxs)
        eduItemList['comments'] = []

        ######################## Set Resume ############################
        records =   ResumeItem()
        
        records['_id']          = str(ObjectId()) 
        records['parent_user']  =   str(''.join(name).encode('utf8',
            errors='ignore').decode('utf8'))
        records['awards']       =   msgpack.packb(str(''.join(
            summary))).decode('utf8', errors='ignore')
        records['skills']       =   msgpack.packb(skills).decode(
            'utf8', errors='ignore')
        records['experience']   = workItemList.encode()
        records['education']    = eduItemList.encode()

        if len(records['parent_user'].strip()) == 0:
            return None

        ######################## DEFAULT ############################
        records['skills']               = None
        records['pubs']                 = None
        records['interests']            = None
        records['languages']            = None
        records['comments_per_section'] = None
        records['todos_per_section']    = None
        
        records['comments']      = []
        records['version']       = 0
        records['num_edits']     = 0
        records['editDt']        = []
        records['slug']          = str(ObjectId())

        return records