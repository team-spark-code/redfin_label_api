BOT_NAME = 'body'

SPIDER_MODULES = ['body.spiders']
NEWSPIDER_MODULE = 'body.spiders'

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'

DOWNLOADER_MIDDLEWARES = {
    'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None,
    'scrapy_user_agents.middlewares.RandomUserAgentMiddleware': 400,
}

ROBOTSTXT_OBEY = False

CONCURRENT_REQUESTS = 16
DOWNLOAD_DELAY = 1  # polite scraping

AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1
AUTOTHROTTLE_MAX_DELAY = 60
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

COOKIES_ENABLED = False

LOG_LEVEL = 'INFO'

# Optional: disable FEEDS output since MongoDB is target
# FEEDS = {}
