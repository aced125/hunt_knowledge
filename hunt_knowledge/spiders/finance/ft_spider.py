import scrapy
from selenium import webdriver
from typing import List, Iterable, Dict, Any
from urllib.parse import urlparse
from collections import defaultdict
import boto3
from hunt_knowledge import utils
import uuid
import datetime
import logging

logger = logging.getLogger(__name__)


class FTSpider(scrapy.Spider):
    name = "ft"
    base_url = "https://www.ft.com/"
    categories = [
        "world",
        "world/uk",
        "companies",
        "technology",
        "markets",
    ]

    def __init__(self):
        super().__init__()
        self.driver = utils.setup_webdriver()
        self.login()

    def login(self):
        self.driver.get("https://www.ft.com")

    def start_requests(self):
        urls = [self.base_url + url for url in self.categories]
        urls = [self.base_url] + urls

        # temp just try front page
        urls = [urls[0]]
        for url in urls:
            yield scrapy.Request(url=url, callback=self.parse)

    def filter_and_process(self, hrefs: Iterable[str]) -> List[Dict[str, Any]]:
        paths = [urlparse(href).path for href in hrefs]

        urls_in_categories = defaultdict(list)
        for href, path in zip(hrefs, paths):
            path_components = path.split("/")
            if len(path_components) != 3:
                continue
            _, cat, href_title = path_components
            try:
                cat = self.categories[self.categories.index(cat)]
                urls_in_categories[cat].append(href)
            except ValueError as e:
                # logger.info(f"Failed cat extraction with err: {e}")
                continue
        no_duplicates_dict = {
            category: list(set(urls)) for category, urls in urls_in_categories.items()
        }
        datalist = [
            self.create_data_object(url, category)
            for category, urls in no_duplicates_dict.items()
            for url in urls
        ]

        return datalist

    @staticmethod
    def create_data_object(url, category):
        nlp = utils.send_pipeline_request(url)
        doc = nlp["doc"]
        return {
            "id": str(uuid.uuid1()),
            "__typename": "Article",
            "createdAt": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[
                :-3
            ]
            + "Z",
            "updatedAt": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[
                :-3
            ]
            + "Z",
            "mercuryObj": {"url": url, "title": nlp["title"], "domain": nlp["source"],},
            "url": url,
            "category": "pharma",
            "subcategory": category,
            "absSum": doc["abstractiveSummary"],
            "title": nlp["title"],
            "source": nlp["source"],
            "text": doc["text"],
        }

    def parse(self, response):
        url = response.url
        hrefs = utils.selenium_get_all_urls_on_page(self.driver, url)
        output = self.filter_and_process(hrefs)
        db = boto3.resource("dynamodb")
        db_name = "CuratedArticlesDB"
        table = db.Table(db_name)
        with table.batch_writer() as batch:
            for item in output:
                batch.put_item(Item=item)
        logger.info(f"Done placing {len(output)} articles in DynamoDB table: {db_name}")
