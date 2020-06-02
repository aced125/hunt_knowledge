import requests
import json
from typing import List
from selenium import webdriver


def setup_webdriver():
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
