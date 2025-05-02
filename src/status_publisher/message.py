from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import mqtt_topics
from status_publisher import VehicleDataPublisher

if TYPE_CHECKING:
    from saic_ismart_client_ng.api.message import MessageEntity

    from publisher.core import Publisher
    from vehicle_info import VehicleInfo


@dataclass(kw_only=True, frozen=True)
class MessagePublisherProcessingResult:
    processed: bool


class MessagePublisher(VehicleDataPublisher):
    def __init__(
        self, vin: VehicleInfo, publisher: Publisher, mqtt_vehicle_prefix: str
    ) -> None:
        super().__init__(vin, publisher, mqtt_vehicle_prefix)
        self.__last_car_vehicle_message = datetime.min

    def on_message(self, message: MessageEntity) -> MessagePublisherProcessingResult:
        if (
            self.__last_car_vehicle_message == datetime.min
            or message.message_time > self.__last_car_vehicle_message
        ):
            self.__last_car_vehicle_message = message.message_time
            self._publish(
                topic=mqtt_topics.INFO_LAST_MESSAGE_TIME,
                value=self.__last_car_vehicle_message,
            )

            if isinstance(message.messageId, str):
                self._publish(
                    topic=mqtt_topics.INFO_LAST_MESSAGE_ID,
                    value=message.messageId,
                )
            else:
                self._transform_and_publish(
                    topic=mqtt_topics.INFO_LAST_MESSAGE_ID,
                    value=message.messageId,
                    transform=lambda x: str(x),
                )

            self._publish(
                topic=mqtt_topics.INFO_LAST_MESSAGE_TYPE,
                value=message.messageType,
            )

            self._publish(
                topic=mqtt_topics.INFO_LAST_MESSAGE_TITLE,
                value=message.title,
            )

            self._publish(
                topic=mqtt_topics.INFO_LAST_MESSAGE_SENDER,
                value=message.sender,
            )

            self._publish(
                topic=mqtt_topics.INFO_LAST_MESSAGE_CONTENT,
                value=message.content,
            )

            self._publish(
                topic=mqtt_topics.INFO_LAST_MESSAGE_STATUS,
                value=message.read_status,
            )

            self._publish(
                topic=mqtt_topics.INFO_LAST_MESSAGE_VIN,
                value=message.vin,
            )

            return MessagePublisherProcessingResult(processed=True)
        return MessagePublisherProcessingResult(processed=False)
