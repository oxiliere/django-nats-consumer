# django-nats-consumer
NATS + Django = ⚡️

## Installation

Please pay attention to the development status; this is Pre-Alpha software; expect the api to evolve as I start using this more in production.

I hope you find some value in it - writing a good consumer takes some finesse.


```bash
pip install django-nats-consumer
```


## Usage

**settings.py**
```python
INSTALLED_APPS = [
    ...
    "nats_consumer",
]

NATS_CONSUMER = {
    "connect_args": {
        "servers": ["nats://localhost:4222"],
        "allow_reconnect": True,
        "max_reconnect_attempts": 5,
        "reconnect_time_wait": 1,
        "connect_timeout": 10,
    },
}
```

**{app_name}/consumers.py**
```python
# Consumers need to be in the consumers module in order to be loaded,
# or you can import them to force them to be loaded.
from nats_consumer import JetstreamPushConsumer

import logging

from nats_consumer import JetstreamPushConsumer, operations

logger = logging.getLogger(__name__)


class OrderConsumer(JetstreamPushConsumer):
    stream_name = "orders"
    subjects = [
        "orders.created",
    ]

    # You need to setup the streams
    async def setup(self):
        return [
            operations.CreateStream(
                name=self.stream_name,
                subjects=self.subjects,
                storage="file"
            ),
        ]

    async def handle_message(self, message):
        # The message only shows if its logged as error
        logger.error(f"Received message: {message.data}")

```

**publish.py**
```python
import asyncio

from nats_consumer import get_nats_client

async def publish_messages():
    ns = await get_nats_client()
    js = ns.jetstream()
    for i in range(5):
        data = {"id": i, "name": f"Order {i}"}
        data_b = json.dumps(data).encode("utf-8")
        print(f"Publishing message {i}...")
        await js.publish("orders.created", data_b)

if __name__ == "__main__":
    asyncio.run(publish_messages())

```

## Running Consumers
**To run a single consumer:**
```bash
python manage.py nats_consumer OrderConsumer --setup
```

**To run multiple consumers:**
```bash
python manage.py nats_consumer OrderConsumer AnotherConsumer
```

**To run all consumers:**
```bash
python manage.py nats_consumer
```

## Feature roadmap
- Encoding/decoding of messages (json, protobuf, etc)
- Better error handling, configurable retry
- Better log output from the consumer
- Configurable DLQ strategies
- [insert your feature here]
