import scrapy
from typing import List, Iterable, Dict, Any
from urllib.parse import urlparse
from collections import defaultdict
import boto3
from hunt_knowledge import utils
import logging

logger = logging.getLogger(__name__)


class FierceBiotechSpider(scrapy.Spider):
    name = "fiercebiotech"
    base_url = "https://www.fiercebiotech.com/"
    db_category = "pharma"
    categories = [
        "biotech",
        "covid-19",
        "research",
        "medtech",
        "cro",
        "cell-gene-therapy",
    ]

    def __init__(self):
        super().__init__()
        self.local_development = False
        self.driver = utils.setup_webdriver(local=self.local_development)
        self.table = boto3.resource("dynamodb").Table("CuratedArticlesDB")

    def start_requests(self):
        urls = [self.base_url + url for url in self.categories]
        urls = [self.base_url] + urls

        # temp just try front page
        urls = [urls[0]]
        for url in urls:
            yield scrapy.Request(url=url, callback=self.parse)

    def process(self, hrefs: Iterable[str]) -> List[Dict[str, Any]]:
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
        logger.info(f"No duplicates dict: {no_duplicates_dict}")
        datalist = [
            utils.url_to_data_object(url, "pharma", subcategory=category)
            for category, urls in no_duplicates_dict.items()
            for url in urls
        ]

        return datalist

    def parse(self, response):
        url = response.url
        urls = utils.selenium_get_all_urls_on_page(self.driver, url)
        logger.info(f"urls: {urls}")

        # Remove duplicates and URLs already in DB
        url_filter = utils.UrlFilterer(period=1, category="pharma")
        urls = list(set(filter(url_filter, urls)))
        logger.info(f"Filtered and unique urls: {urls}")

        output = self.process(urls)
        logger.info(f"Output: {output}")

        if not self.local_development:
            with self.table.batch_writer() as batch:
                for item in output:
                    batch.put_item(Item=item)
            logger.info(f"Done placing {len(output)} articles in DynamoDB table")
