"""
scrape.py: Alternate to Scrapy spider, which does the scraping
manually from links provided rather than through redirection

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
from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

import msgpack
from bson.objectid import ObjectId

from bs4 import BeautifulSoup
import sys
from dateutil import parser

from plytos.models.resume import (Resume, Experience, Education, 
    Awards, WorkItem, EducationItem, AwardItem)

def _get_html(link):
    sess = requests.Session()
    retries = Retry(total=25, backoff_factor=0.1)
    sess.mount('http://', HTTPAdapter(max_retries=retries))
    return sess.get(link).content

def parse(link):
    html = _get_html(link)
    soup = BeautifulSoup(html, "lxml")

    digest  =   soup.find("ol", attrs={"class" : "resultsList"})
    url_prefix = 'http://www.indeed.com'

    names          =   [name.text.strip() for name in 
        soup.find_all("a", attrs={"target" : "_blank"})]
    links          =   [link['href'] for link in soup.find_all("a", 
            href=True, attrs={"target" : "_blank"})]
    
    if len(links) == 0:
        return

    count = 0
    for name, link in zip(names, links):
        full_url = url_prefix + link
        if name not in 'Feedback':
            resume_html = _get_html(full_url)
            resume_soup = BeautifulSoup(resume_html, "lxml")
            resume      = parse_page(resume_soup)
        resume.save()
        print("Completed Resume")

def get_work(resume_soup):
    workHistory =   []
    experience = resume_soup.find_all("div", attrs={"class" : 
        "work-experience-section"})
    for elem in experience:
        workEntry   =   WorkItem()

        try:
            position       =   elem.find("p", attrs={"class" : 
                "work_title title"}).text.strip()
            workEntry.position  =   position
        except: position = ""

        try:
            company =   elem.find("div", attrs={"class" : 
                "work_company"}).find("span").text.strip()
            workEntry.company =   company
        except: company = ""

        try: 
            dates     = elem.find("p", attrs={"class" :
                "work_dates"}).text.strip()
            dates_str   =   dates.split('to')
        except: dates_str = []

        workEntry.startDt =   None
        workEntry.endDt   =   None
        if len(dates_str) > 0:
            try:
                workEntry.startDt =   parser.parse(dates_str[0].strip().encode(
                    'utf8', errors='ignore').decode('utf8'))
            except: workEntry.startDt = None
        if len(dates_str) > 1:
            try:
                workEntry.endDt   =   parser.parse(dates_str[1].strip().encode(
                    'utf8', errors='ignore').decode('utf8'))
            except: workEntry.endDt = None

        try:
            description       =   elem.find("p", attrs={"class" : 
                "work_description"}).text.strip()
        except: description = ""
        workEntry.highlights    =   [str(''.join(description))]

        ################### DEFAULT #######################
        workEntry._id          = str(ObjectId())
        workEntry.url          = ""
        workEntry.skills       = []

        workHistory.append(workEntry)
    return workHistory

def get_edu(resume_soup):
    eduHistory =   []
    education  =   resume_soup.find_all("div", attrs={"class" : 
        "education-section"})
    for elem in education:
        eduEntry    =   EducationItem()

        try:
            degree      =   elem.find("p", 
                attrs={"class" : "edu_title"}).text.strip()
        except: degree = ""
        eduEntry.degree  =   str(''.join(degree))

        try:
            school      =   elem.find("div", 
                attrs={"class" : "edu_school"}).find("span").text.strip()
        except: school = ""
        eduEntry.school  =   str(''.join(school))

        try:
            locale      =   elem.find("span", 
                attrs={"itemprop" : "addressLocality"}).text.strip()
        except: locale = ""
        eduEntry.locale  =   str(''.join(locale))
            
        try:
            grad_date   =   [date.text.strip() for date in 
                elem.find_all("p", attrs={"class" : "edu_dates"})]
            dates_str   =   str(''.join(grad_date)).split(' to ')
        except: grad_date = []

        eduEntry.gradDt   =   None
        eduEntry.startDt  =   None
        if len(grad_date) > 0:
            try:
                eduEntry.gradDt = parser.parse(dates_str[0].encode(
                    'utf8', errors='ignore').decode('utf8'))
            except: eduEntry.gradDt = None
        if len(grad_date) > 1:
            try:
                eduEntry.startDt = parser.parse(dates_str[1].encode(
                    'utf8', errors='ignore').decode('utf8'))
            except: eduEntry.startDt = None

        ################### DEFAULT #######################
        eduEntry._id       = str(ObjectId())
        eduEntry.gpa       = 0.0
        eduEntry.courses   = []

        eduHistory.append(eduEntry)
    return eduHistory

def parse_page(resume_soup):
    resume =   Resume()
    resume._id          = str(ObjectId()) 

    try:
        name = resume_soup.find("h1", attrs={"id" : "resume-contact"}).text.strip()
        resume.parent_user  =   str(''.join(name).encode('utf8',
            errors='ignore').decode('utf8'))
    except: pass

    try:
        headline = resume_soup.find("h2", attrs={"id" : "headline"}).text.strip()
    except: pass

    try:
        summary = resume_soup.find("p", attrs={"id" : "res_summary",
            "class": "summary"}).text.strip()

        award_item = AwardItem()
        award_item.desc = msgpack.packb(str(''.join(
            summary))).decode('utf8', errors='ignore').strip()

        award = Awards(
            items=[award_item],
            comments=[]
        )
        resume.awards = award
    except: pass

    skills      =   []
    try:
        skill       =   [skill.text.strip() for skill in resume_soup.find("div", 
            attrs={"id" : "skills-items", "class": "items-container"}).find_all("span")]
    except: skill = ""
    if len(skill) != 0:
        skills.append(str(''.join(skill)))

    try:
        skill       =  [skill.text.strip() for skill in resume_soup.find("div", 
            attrs={"id" : "additionalinfo-section", "class": "last"}).find("div", 
            attrs={"class" : "data_display"}).find_all("p")]
    except: skill = ""
    if len(skill) != 0:
        skills.append(str(''.join(skill)))        
        
    if len(skills) > 0:
        resume.skills       =   msgpack.packb(skills).decode(
            'utf8', errors='ignore')

    resume_links    =   []
    try:
        links       =   [link.text.strip() for link in resume_soup.find("div", 
            attrs={"id" : "link-items", "class": "items-container"}).find_all("p")]
    except: links = []
    for link in links:
        resume_links.append(str(''.join(link)))

    workItemList = Experience()
    workItemList._id      = str(ObjectId()) 
    workItemList.items    = get_work(resume_soup)
    workItemList.comments = []

    eduItemList = Education()
    eduItemList._id      = str(ObjectId()) 
    eduItemList.items    = get_edu(resume_soup)
    eduItemList.comments = []

    ######################## Set Resume ############################
    resume.experience   = workItemList
    resume.education    = eduItemList

    if len(resume.parent_user.strip()) == 0:
        return None

    ######################## DEFAULT ############################
    resume.skills               = None
    resume.pubs                 = None
    resume.interests            = None
    resume.languages            = None
    resume.comments_per_section = None
    resume.todos_per_section    = None
        
    resume.comments      = []
    resume.version       = 0
    resume.num_edits     = 0
    resume.editDt        = []
    resume.slug          = str(ObjectId())

    return resume

def populate_db():
    MAX_SCRAPES = 100
    INCREMENT = 50

    # Put True if you want to scrape a particular URL
    start_urls = {
        'http://www.indeed.com/resumes/statistics-python': True,
        'http://www.indeed.com/resumes/data-scientist': True,
        #'http://www.indeed.com/resumes/python': True,
        #'http://www.indeed.com/resumes/java': True,
        #'http://www.indeed.com/resumes/SAS': True,
        #'http://www.indeed.com/resumes/javascript': True,
        #'http://www.indeed.com/resumes/marketing-analyst': True,
        #'http://www.indeed.com/resumes/biomedical': True,
        #'http://www.indeed.com/resumes/physicist': True,
        #'http://www.indeed.com/resumes/business-analyst': True,
        #'http://www.indeed.com/resumes/writer': True,
        #'http://www.indeed.com/resumes/product-manager': True,
        #'http://www.indeed.com/resumes/produce-manager': True,
        #'http://www.indeed.com/resumes/technical-writer': True,
        #'http://www.indeed.com/resumes/photographer': True,
        #'http://www.indeed.com/resumes/dev-ops': True,
        #'http://www.indeed.com/resumes/architect': True,
        #'http://www.indeed.com/resumes/civil-engineer': True,
        #'http://www.indeed.com/resumes/graphic-designer': True,
        #'http://www.indeed.com/resumes/electrical-engineer': True,
        #'http://www.indeed.com/resumes/server': True,
        #'http://www.indeed.com/resumes/translator': True,
        #'http://www.indeed.com/resumes/animator': True
    }

    for url in start_urls:
        if start_urls[url]:
            for start in range(0, MAX_SCRAPES, INCREMENT):
                link = "{}?start={}".format(url, start)
                parse(link)
        print("Completed: {}".format(url))

if __name__ == "__main__":
    populate_db()