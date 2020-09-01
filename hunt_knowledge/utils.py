import requests
import json
from typing import List
from selenium import webdriver
import uuid
import boto3
from boto3.dynamodb.conditions import Key
from datetime import datetime, date, timedelta

import logging

logger = logging.getLogger(__name__)
# logger.addHandler(logging.StreamHandler())  # Writes to console
logger.setLevel(logging.DEBUG)
logging.getLogger("boto3").setLevel(logging.CRITICAL)
logging.getLogger("botocore").setLevel(logging.CRITICAL)
logging.getLogger("s3transfer").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)


def setup_webdriver(local=False):
    if local:
        return webdriver.Chrome("/usr/bin/chromedriver")
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--window-size=1420,1080")
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=chrome_options)
    return driver


def selenium_get_all_urls_on_page(driver, url, drop_duplicates=True) -> List[str]:
    """Given a URL, get all URLs on that URL"""
    driver.get(url)
    elements = driver.find_elements_by_xpath("//a[@href]")
    urls = []
    for elem in elements:
        href = elem.get_attribute("href")
        urls.append(href)
    if drop_duplicates:
        urls = list(set(urls))
    return urls


def send_pipeline_request(url):
    # api = "http://ac6b3caf43dd145eb8bd6baf06aa83aa-e02d1280de19e099.elb.eu-west-1.amazonaws.com/genei-pipeline"
    api = "https://w3ddy8vzni.execute-api.eu-west-1.amazonaws.com/v1/genei-pipeline"
    headers = {"Content-type": "application/json"}
    generation_args = {
        "beam": 8,
        "min_len": 50,
        "max_len": 300,
        "len_pen": 1.0,
        "no_repeat_ngram_size": 3,
        "return_sents": True,
    }
    data = {
        "config": {"generation_args": generation_args},
        "disabledComponents": [
            "ReduceEntityVectorsComponent",
            "HierarchicalEntTagger",
            "MultiEntReducer",
            "ImageSearcher",
        ],
        "url": url,
    }
    logger.info(f"Making pipeline request with url: {url}")
    return requests.post(api, headers=headers, data=json.dumps(data)).json()


def get_url_summary(url):
    response = send_pipeline_request(url)
    doc = response["doc"]
    summary = doc["abstractiveSummary"]
    return summary


def nlp_object_to_data_object(nlp, category, subcategory=None):
    """Convert NLP object to object ready to be placed in DB."""
    doc = nlp["doc"]
    metadata = nlp["metadata"]
    metadata.update({"domain": nlp["source"]})
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    updatedAt = metadata.get("date_published")
    if updatedAt is None:
        updatedAt = now

    return {
        "id": str(uuid.uuid1()),
        "__typename": "Article",
        "createdAt": now,
        "updatedAt": updatedAt,
        "mercuryObj": metadata,
        "url": metadata.get("url"),
        "category": category,
        "subcategory": subcategory,
        "absSum": doc["abstractiveSummary"],
        "title": nlp["title"],
        "source": nlp["source"],
        "text": doc["text"],
    }


def url_to_data_object(url, category, subcategory=None):
    nlp = send_pipeline_request(url)
    obj = nlp_object_to_data_object(nlp, category, subcategory)
    obj["url"] = url
    return obj


def query_dynamo_by_category(
    period: int = 1, table_name: str = "CuratedArticlesDB", category: str = "pharma"
):
    """
    Queries any DynamoDB table by category, up to X previous days.
    Parameters
    ----------
    period: The number of days we want to go back
    table_name: Name of the DynamoDB table
    category: The category of the articles. E.g "pharma"

    Returns
    -------
    Responses of database
    """
    # Get yesterday's date
    yday = str(date.today() - timedelta(days=period))

    table = boto3.resource("dynamodb").Table(table_name)
    return table.query(
        IndexName="category-createdAt-index",
        KeyConditionExpression=Key("category").eq(category) & Key("createdAt").gt(yday),
    )


def query_fields_of_category(
    field="title", period=1, table_name="CuratedArticlesDB", category="pharma"
):
    """Gets data field of articles of a particular category from the DB."""
    response = query_dynamo_by_category(period, table_name, category)
    if not response["Items"]:
        return []
    obj = response["Items"][0]
    assert field in obj, f"Field {field} not in object with keys: {obj.keys()}"
    return [x[field] for x in response["Items"]]


def standardize_url(url):
    return url[:-1] if url.endswith("/") else url


class UrlFilterer:
    """Class to filter URLs that are already in the database from the last X days"""

    def __init__(
        self,
        period: int = 1,
        table_name: str = "CuratedArticlesDB",
        category: str = "pharma",
    ):
        urls = query_fields_of_category("url", period, table_name, category)
        self.urls = [standardize_url(url) for url in urls]
        self.period = period
        self.table_name = table_name
        self.category = category

    def __repr__(self):
        return (
            f"{__class__.__name__}, period: {self.period}, "
            f"table_name: {self.table_name}, "
            f"category: {self.category}"
        )

    def __call__(self, url):
        url = standardize_url(url)
        return url not in self.urls


def is_title_in_db(
    title,
    period: int = 1,
    table_name: str = "CuratedArticlesDB",
    category: str = "pharma",
):
    """Checks if article title already exists in the last X days."""
    titles = query_fields_of_category("title", period, table_name, category)
    return title in titles
