import logging

from nats_consumer import JetstreamPushConsumer, operations

logger = logging.getLogger(__name__)


class OrderConsumer(JetstreamPushConsumer):
    stream_name = "orders"
    subjects = [
        "orders.created",
    ]

    async def setup(self):
        return [
            operations.CreateStream(
                name=self.stream_name,
                subjects=self.subjects,
                storage="file",
            ),
        ]

    async def handle_message(self, message):
        # The message only shows if its logged as error
        logger.error(f"Received message: {message.data}")
