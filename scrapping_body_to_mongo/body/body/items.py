# items.py
import scrapy

class ArticleItem(scrapy.Item):
    link = scrapy.Field()
    title = scrapy.Field()
    published = scrapy.Field()
    body = scrapy.Field()
    domain = scrapy.Field()
