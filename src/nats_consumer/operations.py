import asyncio
import nats
from django.conf import settings
from django.db.migrations import RunPython
from nats.js.api import StreamConfig

from .consumer import get_nats_client


class StreamOperation(RunPython):
    def __init__(self, *args, **kwargs):
        def wrap_execute(apps, schema_editor):
            asyncio.run(self.execute())

        super().__init__(wrap_execute)


class CreateStream(StreamOperation):
    """
    Helper to create a stream
    """

    def __init__(self, stream_name, **kwargs):
        self.stream_name = stream_name
        self.config = {**kwargs}
        super().__init__()

    async def execute(self, nats_client=None):
        created_client = False
        try:
            if nats_client is None:
                nats_client = await get_nats_client()

            js = nats_client.jetstream()
            config = StreamConfig(name=self.stream_name, **self.config)
            await js.add_stream(config)
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

            # Logic to delete a JetStream stream
            await nats_client.jetstream().delete_stream(name=self.stream_name)
        finally:
            if created_client and nats_client:
                await nats_client.drain()
                await nats_client.close()


class UpdateStream(StreamOperation):
    """
    Helper function to update a stream
    """

    def __init__(self, stream_name, **kwargs):
        self.stream_name = stream_name
        self.config = dict(**kwargs)
        super().__init__()

    async def execute(self, nats_client=None):
        created_client = False
        try:
            if nats_client is None:
                nats_client = await get_nats_client()
                created_client = True

            # Fetch the current stream configuration
            stream_info = nats_client.jetstream().stream_info(self.stream_name)
            config = stream_info.config
            for attr, value in self.config:
                if has_attr(config, attr):
                    setattr(config, attr, value)
                else:
                    raise AttributeError(f"{attr} does not exist on {config}.")

            # Apply the updated configuration
            await nats_client.jetstream().update_stream(config)

        finally:
            if created_client and nats_client:
                await nats_client.drain()
                await nats_client.close()
