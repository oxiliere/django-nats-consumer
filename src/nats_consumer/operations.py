import asyncio
import logging

from django.db.migrations import RunPython
from nats.js import api
from nats.js.errors import NotFoundError

from .client import get_nats_client

__all__ = [
    "StreamOperation",
    "CreateStream",
    "DeleteStream",
    "UpdateStream",
    "CreateOrUpdateStream",
    # This is just for ease of use:
    "api",
]

logger = logging.getLogger(__name__)


class StreamOperation(RunPython):
    def __init__(self, *args, **kwargs):
        def wrap_execute(apps, schema_editor):
            asyncio.run(self.execute())

        super().__init__(wrap_execute)


class CreateStream(StreamOperation):
    """
    Helper to create a stream
    """

    def __init__(self, **kwargs):
        self.config = api.StreamConfig(**kwargs)
        super().__init__()

    async def execute(self, nats_client=None):
        created_client = False
        try:
            if nats_client is None:
                nats_client = await get_nats_client()
                created_client = True
            js = nats_client.jetstream()
            try:
                await js.stream_info(self.config.name)
                logger.warning(f"Stream {self.config.name} already exists.")
            except NotFoundError:
                await js.add_stream(self.config)
                logger.info(f"Stream {self.config.name} created.")
        finally:
            if created_client and nats_client:
                await nats_client.drain()
                await nats_client.close()


class DeleteStream(StreamOperation):
    """
    Helper function to delete a stream
    """

    def __init__(self, stream_name):
        self.stream_name = stream_name
        super().__init__()

    async def execute(self, nats_client=None):
        created_client = False
        try:
            if nats_client is None:
                nats_client = await get_nats_client()
                created_client = True

            js = nats_client.jetstream()
            try:
                await js.stream_info(self.stream_name)
                await js.delete_stream(self.stream_name)
                logger.info(f"Stream {self.stream_name} deleted.")
            except NotFoundError:
                logger.warning(f"Stream {self.stream_name} does not exist.")
        finally:
            if created_client and nats_client:
                await nats_client.drain()
                await nats_client.close()


class UpdateStream(StreamOperation):
    """
    Helper function to update a stream
    """

    def __init__(self, **kwargs):
        self.config = api.StreamConfig(**kwargs)
        super().__init__()

    async def execute(self, nats_client=None):
        created_client = False
        try:
            if nats_client is None:
                nats_client = await get_nats_client()
                created_client = True

            try:
                js = nats_client.jetstream()
                await js.stream_info(self.config.name)
                await js.update_stream(self.config)
            except NotFoundError:
                logger.warning(f"Stream {self.config.name} does not exist.")
                return

        finally:
            if created_client and nats_client:
                await nats_client.drain()
                await nats_client.close()


class CreateOrUpdateStream(StreamOperation):
    """
    Helper function to create or update a stream
    """

    def __init__(self, **kwargs):
        self.config = api.StreamConfig(**kwargs)
        super().__init__()

    async def execute(self, nats_client=None):
        created_client = False
        try:
            if nats_client is None:
                nats_client = await get_nats_client()
                created_client = True

            try:
                js = nats_client.jetstream()
                await js.stream_info(self.config.name)
                await js.update_stream(self.config)
                logger.info(f"Stream {self.config.name} updated.")
            except NotFoundError:
                await js.add_stream(self.config)
                logger.info(f"Stream {self.config.name} created.")

        finally:
            if created_client and nats_client:
                await nats_client.drain()
                await nats_client.close()
