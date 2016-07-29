from twisted.internet import reactor
from scrapy.crawler import Crawler
from scrapy.settings import Settings

from bson.objectid import ObjectId

from scraper.scraper.spiders.resume_spider import ResumeIndeedSpider
# from models.resume import Awards, Experience, Education, Resume

def get_resume(awards, experience, education, parent_user, skills):
    resume_awards = Awards(
        _id=ObjectId(),
        items=awards,
        comments=[]
    )

    resume_experience = Experience(
        _id=ObjectId(),
        items=experience,
        comments=[]
    )

    resume_education = Education(
        _id=ObjectId(),
        items=education,
        comments=[]
    )

    resume = Resume(
        parent_user=parent_user,
        skills=skills,
        
        awards=resume_awards,
        experience=resume_experience,
        education=resume_education
    )
    return resume

# Usage
if __name__ == "__main__":
    spider = ResumeIndeedSpider()
    crawler = Crawler(spider, Settings())
    crawler.configure()
    crawler.crawl(spider)
    crawler.start()
    reactor.run() 