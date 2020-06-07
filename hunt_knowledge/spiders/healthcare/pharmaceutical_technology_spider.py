import scrapy
import boto3
from hunt_knowledge import utils
import itertools
import logging

logger = logging.getLogger(__name__)


class PharmaceuticalTechnologySpider(scrapy.Spider):
    name = "pharmaceuticaltechnology"
    base_url = "https://www.pharmaceutical-technology.com/"
    blacklist = ["https://www.pharmaceutical-technology.com/deal-news/"]

    db_category = "pharma"
    categories = ["news", "features"]

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
        urls = [self.base_url + "deals/"]
        for url in urls:
            yield scrapy.Request(url=url, callback=self.parse)

    def create_data_object(self, url, subcategory=None):
        return utils.url_to_data_object(url, self.db_category, subcategory)

    def parse(self, response):
        def make_xpath(cls):
            return f"//div[@class='{cls}']//a/@href"

        main_feature = response.xpath(make_xpath("main-feature")).extract()
        article_grid_urls = response.xpath(make_xpath("article-grid")).extract()
        most_read_urls = response.xpath(make_xpath("si most-read")).extract()
        news_and_analyses = response.xpath(make_xpath("cards cat-landp")).extract()

        logger.warning(f"Main feature: {main_feature}")
        logger.warning(f"Grid: {article_grid_urls}")
        logger.warning(f"Most read: {most_read_urls}")
        logger.warning(f"News and analysis: {news_and_analyses}")

        all_urls = [main_feature, article_grid_urls, most_read_urls, news_and_analyses]
        all_urls = itertools.chain(*all_urls)

        def filter_valid_url(url):
            url_valid = not url.startswith(self.base_url + ".")
            url_not_in_blacklist = not any([url in self.blacklist])
            cat_in_url = any([cat in url for cat in self.categories])
            return url_valid and cat_in_url and url_not_in_blacklist

        # Remove invalid and duplicate URLs
        all_urls = list(set(filter(filter_valid_url, all_urls)))

        logger.warning(f"All urls: {all_urls}")

        # Remove URLs already in the DB
        url_filter = utils.UrlFilterer(period=1, category="pharma")
        urls_not_in_db = list((filter(url_filter, all_urls)))

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
