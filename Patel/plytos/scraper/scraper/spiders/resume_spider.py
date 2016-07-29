#!/usr/bin/env python
import types
import time
from datetime import date, datetime, timedelta

import requests
import msgpack

from scrapy import Spider
from scrapy.shell import inspect_response
from scrapy.spiders import Rule
from scrapy.linkextractors import LinkExtractor
from scrapy.selector import Selector

from scraper.scraper.items import ResumeItem, WorkItem, SchoolItem, ItemList

class ResumeIndeedSpider(Spider):
    name = "resume"
    allowed_domains = ["indeed.com"]
    start_urls = ['http://www.indeed.com/resumes/statistics-python',
                  'http://www.indeed.com/resumes/data-scientist',
                  'http://www.indeed.com/resumes/python',
                  'http://www.indeed.com/resumes/java',
                  'http://www.indeed.com/resumes/SAS',
                  'http://www.indeed.com/resumes/javascript',
                  'http://www.indeed.com/resumes/marketing-analyst']

    rules = (Rule(LinkExtractor(
        restrict_xpaths = ('//a[@class="instl confirm-nav next"]')), 
        callback = "parse_item", follow = True),)

    def parse(self, response):
        hxs     =   Selector(response)
        digest  =   hxs.xpath('//ol[@class="resultsList"]')
        records =   ResumeItem()
        
        url_prefix = 'http://www.indeed.com'

        resume_links   =   digest.xpath('//li[@class="sre"]//div[@class="sre-entry"]')
        names   =   digest.xpath('//a[@target="_blank"]/text()').extract()
        links   =   digest.xpath('//a[@target="_blank"]/@href').extract()
                
        for name, link in zip(names, links):
            if name not in 'Feedback':
                records['parent_user'] =   name
                if "http://" not in link:
                    link =   url_prefix + link

                records = self.parse_node(requests.get(link))
                yield records

    def parse_node(self, response):
        hxs     =   Selector(response)
        # inspect_response(response, self)
        records =   ResumeItem()
        
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

        workHistory =   ItemList()
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

                workHistory.items.append(workEntry)
                
        eduHistory =   ItemList()
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

                eduHistory.items.append(eduEntry)

        # volunteer
        records['parent_user']     =   str(''.join(name).encode('utf8',
            errors='ignore'))
        records['awards']  =   str(msgpack.packb(str(''.join(
            summary))).decode('utf8', errors='ignore'))
        records['skills']   =   str(msgpack.packb(skills).decode(
            'utf8', errors='ignore'))
        records['experience'] = workHistory
        records['education']    = str(msgpack.packb(eduHistory, 
            default=eduHistory.encode).decode('utf8', errors='ignore'))
        return records