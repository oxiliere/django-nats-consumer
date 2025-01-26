import asyncio
import inspect
import logging
import os
from typing import List, Optional

import nats
from nats.aio.client import Client as NATS
from nats.errors import TimeoutError
from nats.js.errors import NotFoundError

from nats_consumer.client import get_nats_client

logger = logging.getLogger(__name__)


def get_module_name(obj):
    try:
        module = inspect.getmodule(obj)
        if module:
            return module.__name__
    except AttributeError:
        pass  # Handle objects without a module (e.g., built-in functions)
    return None


CONSUMERS = {}


def validate_stream_name(stream_name):
    if " " in stream_name:
        raise ValueError("Stream name cannot contain spaces")
    elif "." in stream_name:
        raise ValueError("Stream name cannot contain dots")
    return stream_name


class ConsumerMeta(type):
    def __new__(cls, name, bases, attrs):
        new_cls = super().__new__(cls, name, bases, attrs)
        base_names = [
            "JetstreamPullConsumer",
            "JetstreamPushConsumer",
            "NatsConsumerBase",
            "NatsConsumer",
        ]
        if name not in base_names:
            stream_name = new_cls.stream_name
            validate_stream_name(stream_name)
            CONSUMERS[name] = new_cls
        return new_cls


class NatsConsumerBase(metaclass=ConsumerMeta):
    stream_name: str
    subjects: List[str]
    deliver_policy: nats.js.api.DeliverPolicy = nats.js.api.DeliverPolicy.ALL

    def __init__(self, nats_client: Optional[NATS] = None, **kwargs):
        self._nats_client = nats_client
        self._running = False
        self._stop_event = asyncio.Event()
        self.message_success_count = 0
        self.message_error_count = 0

    @classmethod
    def get_consumer(cls, name):
        return CONSUMERS[name]

    @classmethod
    async def stream_exists(cls):
        nats_client = await get_nats_client()
        js = nats_client.jetstream()
        try:
            await js.stream_info(cls.stream_name)
            return True
        except NotFoundError:
            return False

    @property
    def consumer_name(self):
        return f"{self.__class__.__name__}"

    @property
    def durable_name(self):
        return f"{self.consumer_name}-{self.hostname}"

    @property
    def hostname(self):
        hostname = os.environ.get("HOSTNAME", "localhost")
        hostname = hostname.replace(".", "-")
        return hostname

    @property
    def deliver_subject(self):
        return f"{self.durable_name}.deliver"

    @property
    def is_connected(self):
        if self._nats_client is None:
            return False
        return self._nats_client.is_connected

    @property
    def is_running(self):
        return self._running

    @property
    async def nats_client(self):
        should_connect = not getattr(self._nats_client, "is_connected", False)
        if self._nats_client is None or should_connect:
            logger.debug("Connecting to NATS")
            self._nats_client = await get_nats_client()
        return self._nats_client

    async def initialize(self):
        pass

    async def message_handler(self, msg):
        raise NotImplementedError("message_handler")

    async def _setup_consumers(self):
        nats_client = await self.nats_client
        js = nats_client.jetstream()
        try:
            consumer_info = await js.consumer_info(self.stream_name, self.durable_name)
            logger.info(f"Retrieved consumer [{self.durable_name}]")
            logger.debug(consumer_info)
        except NotFoundError:
            config = nats.js.api.ConsumerConfig(
                deliver_policy=self.deliver_policy,
                deliver_subject=self.deliver_subject,
            )
            await js.add_consumer(
                self.stream_name,
                durable_name=self.durable_name,
                config=config,
            )
            logger.info(f"Created consumer [{self.durable_name}]")
        except Exception as e:
            logger.error(f"Error creating consumer: {str(e)}")
            raise e

    async def start(self):
        await self._setup_consumers()
        await self.initialize()
        self._running = True

    async def stop(self):
        if not self._stop_event.is_set():
            self._stop_event.set()
            nats_client = await self.nats_client
            if nats_client:
                try:
                    if hasattr(self, "subscriptions"):
                        for sub in self.subscriptions:
                            await sub.unsubscribe()
                    await nats_client.close()
                except Exception as e:
                    logger.error(f"Error draining NATS client: {str(e)}")
            self._running = False

    async def wrap_handle_message(self, msg):
        try:
            await self.handle_message(msg)
            await msg.ack()
            self.message_success_count += 1
        except Exception as e:
            await msg.nak()
            self.message_error_count += 1
            logger.error(f"Error handling message: {str(e)}")


class JetstreamPushConsumer(NatsConsumerBase):
    async def run(self, timeout: Optional[int] = None):
        await self.start()
        sub = None
        try:
            nats_client = await self.nats_client
            js = nats_client.jetstream()
            for subject in self.subjects:
                sub = await js.subscribe(
                    subject=subject, durable=self.durable_name, stream=self.stream_name, cb=self.wrap_handle_message
                )
            await asyncio.Future()
        except Exception as e:
            logger.error(f"Error in consumer: {str(e)}")
        finally:
            if sub:
                await sub.unsubscribe()
            await self.stop()


class JetstreamPullConsumer(NatsConsumerBase):
    def __init__(self, nats_client: Optional[NATS] = None, **kwargs):
        super().__init__(nats_client, **kwargs)
        self.subscriptions = []

    async def initialize(self):
        await self.set_subscriptions()

    async def set_subscriptions(self):
        nats_client = await self.nats_client
        js = nats_client.jetstream()
        subscriptions = []
        for subject in self.subjects:
            sub = await js.pull_subscribe(
                subject=subject,
                durable=self.durable_name,
                stream=self.stream_name,
            )
            subscriptions.append(sub)
        logger.info(f"Set subscriptions for {self.consumer_name}:")
        self.subscriptions = subscriptions

    async def run(self, batch_size: int = 100, timeout: Optional[int] = None):
        await self.start()
        try:
            while self.is_running and not self._stop_event.is_set():
                logger.warn(".")
                for sub in self.subscriptions:
                    try:
                        batch_args = {"timeout": timeout} if timeout else {}
                        messages = await sub.fetch(batch=batch_size, **batch_args)
                        logger.info(f"Consumer[{self.consumer_name}] received {len(messages)} messages")
                        tasks = [self.wrap_handle_message(msg) for msg in messages]
                        if tasks:
                            await asyncio.gather(*tasks)
                    except TimeoutError:
                        if not self.is_connected:
                            logger.warn(f"TimeoutError: {sub}")
                            await self.set_subscriptions()
                        continue
                    except Exception as e:
                        logger.error(f"Error processing messages: {str(e)}")
                        self._stop_event.set()
        except Exception as e:
            logger.error(f"Error in consumer: {str(e)}")
        finally:
            logger.info("Stopping consumer")
            await self.stop()


class NatsConsumer:
    @classmethod
    def get(cls, consumer_name):
        return CONSUMERS[consumer_name]

    @classmethod
    def filter(cls, consumer_names):
        if not consumer_names:
            return list(CONSUMERS.values())
        return [cls.get(consumer_name) for consumer_name in consumer_names]
