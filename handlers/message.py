import datetime
import logging
from typing import Union

from saic_ismart_client_ng import SaicApi
from saic_ismart_client_ng.api.message.schema import MessageEntity
from saic_ismart_client_ng.exceptions import SaicApiException

from handlers.vehicle import VehicleHandlerLocator
from vehicle import RefreshMode

LOG = logging.getLogger(__name__)


class MessageHandler:
    def __init__(self, gateway: VehicleHandlerLocator, saicapi: SaicApi):
        self.gateway = gateway
        self.saicapi = saicapi
        self.last_message_ts = datetime.datetime.min
        self.last_message_id = None

    async def check_for_new_messages(self) -> None:
        if self.__should_poll():
            try:
                LOG.debug("Checking for new messages")
                await self.__polling()
            except Exception as e:
                LOG.exception('MessageHandler poll loop failed', exc_info=e)
        else:
            LOG.debug("Not checking for new messages since all cars have RefreshMode.OFF")

    async def __polling(self):
        try:
            all_messages = await self.__get_all_alarm_messages()
            LOG.info(f'{len(all_messages)} messages received')

            new_messages = [m for m in all_messages if m.read_status != 'read']
            for message in new_messages:
                LOG.info(message.details)
                await self.__read_message(message)

            latest_message = self.__get_latest_message(all_messages)
            if latest_message.messageId != self.last_message_id and latest_message.message_time > self.last_message_ts:
                self.last_message_id = latest_message.messageId
                self.last_message_ts = latest_message.message_time
                LOG.info(
                    f'{latest_message.title} detected at {latest_message.message_time}'
                )
                vehicle_handler = self.gateway.get_vehicle_handler(latest_message.vin)
                if vehicle_handler:
                    vehicle_handler.vehicle_state.notify_message(latest_message)

            # Delete vehicle start messages unless they are the latest
            vehicle_start_messages = [
                m for m in all_messages
                if m.messageType == '323' and m.messageId != self.last_message_id
            ]
            for vehicle_start_message in vehicle_start_messages:
                await self.__delete_message(vehicle_start_message)

        except SaicApiException as e:
            LOG.exception('MessageHandler poll loop failed during SAIC API Call', exc_info=e)
        except Exception as e:
            LOG.exception('MessageHandler poll loop failed unexpectedly', exc_info=e)

    async def __get_all_alarm_messages(self) -> list[MessageEntity]:
        idx = 1
        all_messages = []
        while True:
            try:
                message_list = await self.saicapi.get_alarm_list(page_num=idx, page_size=1)
                if message_list.messages and len(message_list.messages) > 0:
                    all_messages.extend(message_list.messages)
                else:
                    return all_messages
                oldest_message = self.__get_oldest_message(all_messages)
                if oldest_message is not None and oldest_message.message_time < self.last_message_ts:
                    return all_messages
            except Exception as e:
                LOG.exception(
                    'Error while fetching a message from the SAIC API, please open the app and clear them, '
                    'then report this as a bug.',
                    exc_info=e
                )
            finally:
                idx = idx + 1

    async def __delete_message(self, latest_vehicle_start_message: MessageEntity):
        try:
            message_id = latest_vehicle_start_message.messageId
            await self.saicapi.delete_message(message_id=message_id)
            LOG.info(f'{latest_vehicle_start_message.title} message with ID {message_id} deleted')
        except Exception as e:
            LOG.exception('Could not delete message from server', exc_info=e)

    async def __read_message(self, message: MessageEntity):
        try:
            message_id = message.messageId
            await self.saicapi.read_message(message_id=message_id)
            LOG.info(f'{message.title} message with ID {message_id} marked as read')
        except Exception as e:
            LOG.exception('Could not mark message as read from server', exc_info=e)

    def __should_poll(self):
        vehicle_handlers = self.gateway.vehicle_handlers or dict()
        refresh_modes = [
            vh.vehicle_state.refresh_mode
            for vh in vehicle_handlers.values()
            if vh.vehicle_state is not None
        ]
        # We do not poll if we have no cars or all cars have RefreshMode.OFF
        if len(refresh_modes) == 0 or all(mode == RefreshMode.OFF for mode in refresh_modes):
            return False
        else:
            return True

    @staticmethod
    def __get_latest_message(vehicle_start_messages: list[MessageEntity]) -> Union[MessageEntity, None]:
        return next(iter(reversed(
            sorted(
                vehicle_start_messages,
                key=lambda m: m.message_time
            )
        )), None)

    @staticmethod
    def __get_oldest_message(vehicle_start_messages: list[MessageEntity]) -> Union[MessageEntity, None]:
        return next(iter(
            sorted(
                vehicle_start_messages,
                key=lambda m: m.message_time
            )
        ), None)
