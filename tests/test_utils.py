from hunt_knowledge import utils


def test_query_dynamodb_by_category():
    response = utils.query_dynamo_by_category(
        period=1, table_name="CuratedArticlesDB", category="pharma"
    )
    assert isinstance(response["Items"], list)
    response_2 = utils.query_dynamo_by_category(
        period=1, table_name="CuratedArticlesDB", category="hacker_news"
    )
    assert isinstance(response_2["Items"], list)
