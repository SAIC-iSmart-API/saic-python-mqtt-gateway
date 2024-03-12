import json
from typing import Optional
from urllib.parse import parse_qs
from urllib.parse import urlparse

from saic_ismart_client_ng.listener import SaicApiListener

from mqtt_topics import INTERNAL_API
from publisher.core import Publisher


class MqttGatewaySaicApiListener(SaicApiListener):
    def __init__(self, publisher: Publisher):
        self.__publisher = publisher

    async def on_request(self, path: str, body: Optional[str] = None, headers: Optional[dict] = None):
        parsed_url = urlparse(path)
        query_string = parse_qs(parsed_url.query)
        if body:
            try:
                body = json.loads(body)
            except:
                pass
        json_message = {
            "path": parsed_url.path,
            "query": query_string,
            "body": body,
            "headers": headers
        }
        topic = parsed_url.path.strip("/")
        self.__publisher.publish_json(
            key=INTERNAL_API + "/" + topic + "/request",
            data=json_message
        )

    async def on_response(self, path: str, body: Optional[str] = None, headers: Optional[dict] = None):
        parsed_url = urlparse(path)
        query_string = parse_qs(parsed_url.query)
        if body:
            try:
                body = json.loads(body)
            except:
                pass
        json_message = {
            "path": parsed_url.path,
            "query": query_string,
            "body": body,
            "headers": headers
        }
        topic = parsed_url.path.strip("/")
        self.__publisher.publish_json(
            key=INTERNAL_API + "/" + topic + "/response",
            data=json_message
        )
