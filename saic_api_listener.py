import json
import logging
from abc import ABC
from typing import Optional, override
from urllib.parse import parse_qs
from urllib.parse import urlparse

from saic_ismart_client_ng.listener import SaicApiListener

from integrations.abrp.api import AbrpApiListener
from mqtt_topics import INTERNAL_API, INTERNAL_ABRP
from publisher.core import Publisher

LOG = logging.getLogger(__name__)


class MqttGatewayListenerApiListener(ABC):
    def __init__(self, publisher: Publisher, topic_prefix: str):
        self.__publisher = publisher
        self.__topic_prefix = topic_prefix

    async def publish_request(self, path: str, body: Optional[str] = None, headers: Optional[dict] = None):
        parsed_url = urlparse(path)
        query_string = parse_qs(parsed_url.query)
        if body:
            try:
                body = json.loads(body)
            except Exception as e:
                LOG.debug("Could not parse body as JSON", exc_info=e)
        json_message = {
            "path": parsed_url.path,
            "query": query_string,
            "body": body,
            "headers": headers
        }
        topic = parsed_url.path.strip("/")
        self.__internal_publish(
            key=self.__topic_prefix + "/" + topic + "/request",
            data=json_message
        )

    async def publish_response(self, path: str, body: Optional[str] = None, headers: Optional[dict] = None):
        parsed_url = urlparse(path)
        query_string = parse_qs(parsed_url.query)
        if body:
            try:
                body = json.loads(body)
            except Exception as e:
                LOG.debug("Could not parse body as JSON", exc_info=e)
        json_message = {
            "path": parsed_url.path,
            "query": query_string,
            "body": body,
            "headers": headers
        }
        topic = parsed_url.path.strip("/")
        self.__internal_publish(
            key=self.__topic_prefix + "/" + topic + "/response",
            data=json_message
        )

    def __internal_publish(self, *, key: str, data: dict):
        if self.__publisher and self.__publisher.is_connected():
            self.__publisher.publish_json(
                key=key,
                data=data
            )
        else:
            LOG.info(f"Not publishing API response to MQTT since publisher is not connected. {data}")


class MqttGatewayAbrpListener(AbrpApiListener, MqttGatewayListenerApiListener):
    def __init__(self, publisher: Publisher):
        super().__init__(publisher, INTERNAL_ABRP)

    @override
    async def on_request(self, path: str, body: Optional[str] = None, headers: Optional[dict] = None):
        await self.publish_request(path, body, headers)

    @override
    async def on_response(self, path: str, body: Optional[str] = None, headers: Optional[dict] = None):
        await self.publish_response(path, body, headers)


class MqttGatewaySaicApiListener(SaicApiListener, MqttGatewayListenerApiListener):
    def __init__(self, publisher: Publisher):
        super().__init__(publisher, INTERNAL_API)

    @override
    async def on_request(self, path: str, body: Optional[str] = None, headers: Optional[dict] = None):
        await self.publish_request(path, body, headers)

    @override
    async def on_response(self, path: str, body: Optional[str] = None, headers: Optional[dict] = None):
        await self.publish_response(path, body, headers)
