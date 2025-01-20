import asyncio
import logging
import json

from django.core.management.base import BaseCommand
from django.conf import settings


from nats_consumer import get_nats_client

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Test NATS Consumers"

    def handle(self, *args, **options):
        try:
            asyncio.run(self.publish_messages())
        except KeyboardInterrupt:
            logger.info("Consumer interrupted by user. Exiting...")

    async def publish_messages(self):
        ns = await get_nats_client()
        js = ns.jetstream()
        print("Publishing messages...")
        for i in range(5):
            data = {"id": i, "name": f"Order {i}"}
            data_b = json.dumps(data).encode("utf-8")
            print(f"Publishing message {i}...")
            await js.publish("orders.created", data_b)
