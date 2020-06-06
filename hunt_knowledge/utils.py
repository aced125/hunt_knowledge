import requests
import json
from typing import List
from selenium import webdriver
import uuid
import boto3
from boto3.dynamodb.conditions import Key
from datetime import datetime, date, timedelta


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


def get_all_hrefs(driver, url,) -> List[str]:
    """Given a URL, get all URLs on that URL"""
    driver.get(url)
    elems = driver.find_elements_by_xpath("//a[@href]")
    hrefs = []
    for elem in elems:
        href = elem.get_attribute("href")
        hrefs.append(href)
    return hrefs


def send_pipeline_request(url):
    api = "http://abeca98336ec911eab3940af5842357b-1941288962.eu-west-1.elb.amazonaws.com/genei-pipeline"
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
    return {
        "id": str(uuid.uuid1()),
        "__typename": "Article",
        "createdAt": metadata["date_published"],
        "updatedAt": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
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
    return nlp_object_to_data_object(nlp, category, subcategory)


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


def query_category_titles(
    period: int = 1, table_name: str = "CuratedArticlesDB", category: str = "pharma"
):
    """Gets titles of articles of a particular category from the DB. """
    response = query_dynamo_by_category(period, table_name, category)
    return [obj["title"] for obj in response["Items"]]


def is_title_in_db(
    title,
    period: int = 1,
    table_name: str = "CuratedArticlesDB",
    category: str = "pharma",
):
    """Checks if article title already exists in the last X days."""
    titles = query_category_titles(period, table_name, category)
    return title in titles
