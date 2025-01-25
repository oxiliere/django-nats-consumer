import asyncio
import logging
import logging.config

from django.core.management.base import BaseCommand

from nats_consumer.consumer import NatsConsumer

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run NATS Consumers"

    def add_arguments(self, parser):
        parser.add_argument("consumer", type=str, help="Consumer name")
        parser.add_argument(
            "--log-level",
            type=str,
            choices=["ERROR", "WARNING", "INFO", "DEBUG"],
            default="INFO",
            help="Log level: ERROR, WARNING, INFO, DEBUG",
        )
        parser.add_argument("--create-stream", action="store_true", help="Setup the stream before running the consumer")

    def handle(self, *args, **options):
        try:
            asyncio.run(self._handle(*args, **options))
        except KeyboardInterrupt:
            logger.info("Consumer interrupted by user. Exiting...")

    async def _handle(self, *args, **options):
        consumer_name = options["consumer"]
        Consumer = NatsConsumer.get(consumer_name)

        await self.run_consumer(Consumer, options)

    async def run_consumer(self, Consumer, options):
        stream_exists = await Consumer.stream_exists()
        if not stream_exists and options["create_stream"]:
            operations = await Consumer().setup()
            for op in operations:
                await op.execute()

        while True:
            try:
                consumer = Consumer()
                await consumer.run()
            except Exception as e:
                logger.error(f"Consumer {Consumer.consumer_name} stopped with error: {e}")
            finally:
                if consumer.is_running:
                    await consumer.stop()
                logger.info(f"Restarting consumer {Consumer.consumer_name}...")
                await asyncio.sleep(1)  # Wait before restarting
