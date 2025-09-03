# spiders/article_extractor_mongo.py
import re
from readability import Document
from bs4 import BeautifulSoup
import scrapy
from pymongo import MongoClient
from body.items import ArticleItem

class ArticleExtractorMongoSpider(scrapy.Spider):
    name = "extractor"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # MongoDB connection
        uri = "mongodb://admin:Redfin7620%21@192.168.0.123:27017/redfin?authSource=admin"
        client = MongoClient(uri)
        self.db = client["redfin"]
        self.source_collection = self.db["entries"]
        self.target_collection = self.db["entries_with_body"]
        
        # Pull all documents from MongoDB
        self.documents = list(self.source_collection.find())

    def start_requests(self):
        for doc in self.documents:
            url = doc.get("link")
            if not url:
                continue
            # Skip if already in target collection
            if self.target_collection.find_one({"link": url}):
                self.logger.info(f"Skipping already processed URL: {url}")
                continue
            yield scrapy.Request(
                url,
                callback=self.parse_article,
                meta={"doc": doc},
                dont_filter=True,
                headers = {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                    "Referer": "https://www.google.com/",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }
            )

    def parse_article(self, response):
        original_doc = response.meta["doc"]
        readability_doc = Document(response.text)
        body_html = readability_doc.summary()
        soup = BeautifulSoup(body_html, "html.parser")

        # Clean and process the HTML
        self.remove_non_content_elements(soup)
        self.process_content_elements(soup)
        clean_text = self.extract_main_content(soup)

        
        # word count check
        
        word_count = len(clean_text.split())
        char_count = len(clean_text)
        if word_count < 50 or char_count < 300:
            self.logger.info(f"Skipping URL due to low word count ({word_count} words, {char_count} chars): {response.url}")
            return  # Stop processing this article

        # --- Prepare output document ---
        # Keep all original fields and just add/update 'body'
        output_doc = original_doc.copy()
        output_doc["body"] = clean_text
        output_doc["text_length"] = char_count

        # Insert into MongoDB target collection
        self.target_collection.insert_one(output_doc)

        # Yield ArticleItem if you use Scrapy pipelines
        yield ArticleItem(
            link=output_doc.get("link"),
            title=output_doc.get("title"),
            published=output_doc.get("published"),
            body=clean_text,
            domain=output_doc.get("domain"),
        )

    # --- Helper methods ---
    def remove_non_content_elements(self, soup):
        for tag in soup.find_all(['nav', 'aside', 'footer', 'header']):
            tag.decompose()
        non_content_selectors = [
            '[class*="nav"]', '[class*="menu"]', '[class*="sidebar"]',
            '[class*="footer"]', '[class*="header"]', '[class*="social"]',
            '[class*="share"]', '[class*="comment"]', '[class*="related"]',
            '[class*="ad"]', '[class*="advertisement"]', '[id*="nav"]',
            '[id*="menu"]', '[id*="sidebar"]', '[id*="footer"]'
        ]
        for selector in non_content_selectors:
            for element in soup.select(selector):
                element.decompose()

    def process_content_elements(self, soup):
        for pre in soup.find_all("pre"):
            pre.string = " [CODE BLOCK] "
        for code in soup.find_all("code"):
            code.decompose()
        for ul in soup.find_all('ul'):
            items = [li.get_text().strip() for li in ul.find_all('li')]
            if items:
                ul.string = " " + " ".join(items) + " "
        for table in soup.find_all('table'):
            table.decompose()
        for header in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            header.string = f" {header.get_text().strip()} "

    def extract_main_content(self, soup):
        text = soup.get_text(separator=" ", strip=True)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
