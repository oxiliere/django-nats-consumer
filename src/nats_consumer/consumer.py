import asyncio
import inspect
import logging
from enum import Enum
from typing import List, Optional

import nats
from nats.aio.client import Client as NATS
from nats.errors import TimeoutError
from nats.js.errors import NotFoundError

from nats_consumer import settings
from nats_consumer.client import get_nats_client
from nats_consumer.exceptions import DjangoNatsError


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


class ErrorAckBehavior(Enum):
    ACK = "Ack"
    NAK = "Nak"
    IMPLEMENTED_BY_HANDLE_ERROR = "ImplementedByHandleError"


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
    filter_subject: Optional[str]
    durable_name: Optional[str]
    deliver_policy: nats.js.api.DeliverPolicy = nats.js.api.DeliverPolicy.ALL

    # TODO: Add retry configuration with defaults
    max_retries: int = 3
    initial_retry_delay: float = 1.0  # seconds
    max_retry_delay: float = 60.0  # seconds
    backoff_factor: float = 2.0
    handle_error_ack_behavior: ErrorAckBehavior = ErrorAckBehavior.NAK  # Default to Nak

    def __init__(self, nats_client: Optional[NATS] = None, **kwargs):
        self._nats_client = nats_client
        self._running = False
        self._stop_event = asyncio.Event()
        self._retry_tasks = {}  # Track retry tasks by message ID
        self._message_attempts = {}  # Track attempts by message GUID
        self.total_success_count = 0
        self.total_error_count = 0
        self.subscriptions = []

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

    def get_durable_name(self):
        if getattr(self, "durable_name", None):
            return self.durable_name
        elif settings.default_durable_name:
            return settings.default_durable_name
        else:
            return "default"

    def get_filter_subject(self) -> str:
        """
        Get the filter subject for the consumer.
        
        Priority:
        1. Explicit filter_subject property
        2. First subject from subjects list (subjects[0])
        3. Error if no subjects available
        """
        if getattr(self, 'filter_subject', None):
            return self.filter_subject
        elif len(self.subjects):
            logger.info(f"No filter_subject specified, using subjects[0]: '{self.subjects[0]}'")
            return self.subjects[0]
        else:
            raise DjangoNatsError("Unable to find the filter subject, please set the filter_subject property or provide subjects")

    @property
    def deliver_subject(self):
        durable_name = self.get_durable_name()
        return f"{durable_name}.deliver"

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

    async def _setup_consumers(self):
        # Subclasses must implement creation appropriate to mode
        return
    
    async def start(self):
        await self._setup_consumers()
        self._running = True

    async def stop(self):
        if not self._stop_event.is_set():
            self._stop_event.set()
            # Cancel all pending retry tasks
            for task in self._retry_tasks.values():
                task.cancel()
            await asyncio.gather(*self._retry_tasks.values(), return_exceptions=True)
            nats_client = await self.nats_client
            if nats_client:
                try:
                    await self.unsubscribe()
                    await nats_client.close()
                except Exception as e:
                    logger.error(f"Error draining NATS client: {str(e)}")
            self._running = False

    def get_message_id(self, msg):
        consumer_id = "unknown"
        # This should exist, but my tests are dumb
        if hasattr(msg.metadata.sequence, "consumer"):
            consumer_id = msg.metadata.sequence.consumer
        message_id = msg.metadata.sequence.stream
        return f"{consumer_id}.{message_id}"

    def _increment_attempt(self, msg):
        guid = self.get_message_id(msg)
        self._message_attempts[guid] = self._message_attempts.get(guid, 0) + 1
        return self._message_attempts[guid]

    def _clear_message_tracking(self, msg):
        guid = self.get_message_id(msg)
        self._message_attempts.pop(guid, None)
        self._retry_tasks.pop(guid, None)

    async def schedule_retry(self, msg, error: Exception):
        attempt = self._increment_attempt(msg)

        # Allow consumer to handle error if implemented
        if attempt > self.max_retries:
            if hasattr(self, "handle_error"):
                await self.handle_error(msg, error, attempt)

            # Determine acknowledgment behavior
            if hasattr(self, "handle_error_ack_behavior"):
                if self.handle_error_ack_behavior == ErrorAckBehavior.ACK:
                    await msg.ack()
                elif self.handle_error_ack_behavior == ErrorAckBehavior.NAK:
                    await msg.nak()
            else:
                await msg.nak()

            self.total_error_count += 1
            self._clear_message_tracking(msg)
            return

        delay = min(self.initial_retry_delay * (self.backoff_factor ** (attempt - 1)), self.max_retry_delay)

        message_id = self.get_message_id(msg)
        logger.info(f"Scheduling retry {attempt} for message {message_id} in {delay} seconds")

        retry_task = asyncio.create_task(self._retry_message(msg, delay, attempt))
        self._retry_tasks[message_id] = retry_task

        try:
            await retry_task
        except asyncio.CancelledError:
            logger.info(f"Retry cancelled for message {message_id}")
        finally:
            self._retry_tasks.pop(message_id, None)

    async def _retry_message(self, msg, delay, attempt):
        await asyncio.sleep(delay)
        try:
            await self.handle_message(msg)
            await msg.ack()
            self.total_success_count += 1
            self._clear_message_tracking(msg)
        except Exception as e:
            message_id = self.get_message_id(msg)
            logger.error(f"Retry attempt {attempt} failed for message {message_id}: {str(e)}")
            await self.schedule_retry(msg, e)

    async def wrap_handle_message(self, msg):
        try:
            await self.handle_message(msg)
            await msg.ack()
            self.total_success_count += 1
            self._clear_message_tracking(msg)
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}")
            await self.schedule_retry(msg, e)

    async def unsubscribe(self):
        for sub in self.subscriptions:
            if sub:
                try:
                    await sub.unsubscribe()
                except Exception as e:
                    logger.error(f"Error unsubscribing from {sub}: {str(e)}")


class JetstreamPushConsumer(NatsConsumerBase):
    async def _add_consumer(self, js, durable_name: str, deliver_subject: str, filter_subject: str):
        try:
            consumer_info = await js.consumer_info(self.stream_name, durable_name)
            logger.info(f"Retrieved consumer [{durable_name}]")
            logger.debug(consumer_info)
        except NotFoundError:
            config = nats.js.api.ConsumerConfig(
                deliver_policy=self.deliver_policy,
                deliver_subject=deliver_subject,
                filter_subject=filter_subject,
                ack_policy=nats.js.api.AckPolicy.EXPLICIT,
            )
            await js.add_consumer(self.stream_name, durable_name=durable_name, config=config)
            logger.info(f"Created consumer [{durable_name}]")
        except Exception as e:
            logger.error(f"Error creating consumer: {str(e)}")
            raise e

    async def _unique_consumer(self, js):
        durable_name = self.get_durable_name()

        await self._add_consumer(
            js=js, durable_name=durable_name,
            deliver_subject=self.deliver_subject,
            filter_subject=self.get_filter_subject()
        )
    
    async def _setup_consumers(self):
        nats_client = await self.nats_client
        js = nats_client.jetstream()
        await self._unique_consumer(js)

    async def _unique_subscription(self, js):
        durable_name = self.get_durable_name()
        sub = await js.subscribe(
            subject=self.deliver_subject, durable=durable_name, stream=self.stream_name, cb=self.wrap_handle_message
        )

        self.subscriptions = [sub]

    async def setup_subscriptions(self):
        nats_client = await self.nats_client
        js = nats_client.jetstream()
        await self._unique_subscription(js)

        await asyncio.Future()

    async def run(self, timeout: Optional[int] = None):
        await self.start()
        try:
            await self.setup_subscriptions()
        except Exception as e:
            logger.error(f"Error in consumer: {str(e)}")
        finally:
            await self.stop()


class JetstreamPullConsumer(NatsConsumerBase):
    async def _add_consumer(self, js, durable_name: str, filter_subject: str):
        try:
            consumer_info = await js.consumer_info(self.stream_name, durable_name)
            logger.info(f"Retrieved consumer [{durable_name}]")
            logger.debug(consumer_info)
        except NotFoundError:
            config = nats.js.api.ConsumerConfig(
                deliver_policy=self.deliver_policy,
                filter_subject=filter_subject,
                ack_policy=nats.js.api.AckPolicy.EXPLICIT,
            )
            await js.add_consumer(self.stream_name, durable_name=durable_name, config=config)
            logger.info(f"Created consumer [{durable_name}]")
        except Exception as e:
            logger.error(f"Error creating consumer: {str(e)}")
            raise e

    async def _unique_consumer(self, js):
        durable_name = self.get_durable_name()
        await self._add_consumer(
            js=js, 
            durable_name=durable_name,
            filter_subject=self.get_filter_subject()
        )
    
    async def _setup_consumers(self):
        nats_client = await self.nats_client
        js = nats_client.jetstream()
        await self._unique_consumer(js)
        
    async def _unique_subscription(self, js):
        durable_name = self.get_durable_name()
        sub = await js.pull_subscribe(
            subject="",  # Empty subject for pull subscription with filter
            durable=durable_name,
            stream=self.stream_name,
        )
        self.subscriptions = [sub]

    async def setup_subscriptions(self):
        nats_client = await self.nats_client
        js = nats_client.jetstream()
        await self._unique_subscription(js)
        logger.info(f"Set subscriptions for {self.consumer_name}: {len(self.subscriptions)} subscription(s)")

    async def run(self, batch_size: int = 100, timeout: Optional[int] = None):
        await self.start()
        try:
            await self.setup_subscriptions()
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
                            await self.setup_subscriptions()
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
