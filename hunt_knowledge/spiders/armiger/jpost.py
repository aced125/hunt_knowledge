import scrapy
import boto3
from hunt_knowledge import utils
import itertools
import logging

logger = logging.getLogger(__name__)


class JPostSpider(scrapy.Spider):
    name = "jpost-middle-east"
    base_url = "https://www.jpost.com/Middle-East"
    blacklist = [""]

    db_category = "armiger"
    categories = [""]

    logging.basicConfig(
        filename="log.txt", format="%(levelname)s: %(message)s", level=logging.WARNING
    )

    def __init__(self):
        super().__init__()
        self.local_development = False
        self.table = boto3.resource("dynamodb").Table("CuratedArticlesDB")

    def start_requests(self):
        # urls = [self.base_url + url for url in self.categories]
        # urls = [self.base_url] + urls
        #
        # # temp just try front page
        # urls = [urls[0]]
        urls = [self.base_url]
        for url in urls:
            yield scrapy.Request(url=url, callback=self.parse)

    def create_data_object(self, url, subcategory=None):
        return utils.url_to_data_object(url, self.db_category, subcategory)

    def parse(self, response):
        def make_xpath(cls):
            return f"//div[@class='{cls}']/a/@href"

        card_articles = response.xpath(make_xpath("itc")).extract()
        logger.warning(f"Card Articles: {card_articles}")

        all_urls = [card_articles]
        all_urls = itertools.chain(*all_urls)

        def filter_valid_url(url):
            url_valid = not url.startswith(self.base_url + ".")
            url_not_in_blacklist = not any([url in self.blacklist])
            # cat_in_url = any([cat in url for cat in self.categories])
            # return url_valid and cat_in_url and url_not_in_blacklist
            return url_valid and url_not_in_blacklist

        # Remove invalid and duplicate URLs
        all_urls = list(set(filter(filter_valid_url, all_urls)))

        logger.warning(f"All urls: {all_urls}")

        # Remove URLs already in the DB
        url_filter = utils.UrlFilterer(period=1, category="armiger")
        urls_not_in_db = list((filter(url_filter, all_urls)))
        urls_not_in_db = urls_not_in_db[:15]

        logger.warning(f"URLs not in db: {urls_not_in_db}")

        output = [self.create_data_object(url) for url in urls_not_in_db]
        logger.warning(f"Output: {output}")

        if not self.local_development:
            with self.table.batch_writer() as batch:
                for item in output:
                    try:
                        batch.put_item(Item=item)
                    except Exception as e:
                        logger.error(
                            f"Failed to put item: {item} in DB " f"with exception: {e}"
                        )
            logger.info(f"Done placing {len(output)} articles in DynamoDB table")
