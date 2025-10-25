# django-nats-consumer
NATS + Django = ⚡️

A powerful Django integration for NATS JetStream with support for both Push and Pull consumers, automatic retry mechanisms, and flexible multi-subject handling.

## Features

- 🚀 **Push & Pull Consumers**: Support for both JetStream consumer types
- 🔄 **Automatic Retries**: Built-in exponential backoff retry mechanism
- 🎯 **Subject Filtering**: Native NATS subject filtering with wildcards
- 🎛️ **Smart Handler Routing**: Automatic message routing based on subjects
- 🛡️ **Error Handling**: Configurable error acknowledgment behaviors
- 📊 **Monitoring**: Built-in success/error counters and logging
- ⚡ **Performance**: Optional uvloop support for better performance
- 🔧 **Django Integration**: Seamless integration with Django management commands

## What's New in This Fork

This fork adds significant enhancements to the original work:
- ✅ Smart handler routing with ConsumerHandler
- ✅ Subject filtering with wildcards  
- ✅ Fallback handling with collision detection
- ✅ Comprehensive test suite with pytest
- ✅ Multi-subject support removal (simplified architecture)s

## Installation

Please pay attention to the development status; this is Pre-Alpha software; expect the api to evolve as I start using this more in production.

```bash
pip install django-nats-consumer
```

### Optional Performance Enhancement
```bash
# For better performance on Unix-like systems
pip install django-nats-consumer[uvloop]
```


## Usage

**settings.py**
```python
INSTALLED_APPS = [
    ...
    "nats_consumer",
    ...
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

## Consumer Types

### Push Consumer with Smart Handler Routing
```python
# {app_name}/consumers.py
from nats_consumer import JetstreamPushConsumer, operations, ErrorAckBehavior
from nats_consumer.handler import ConsumerHandler
import logging
import json

logger = logging.getLogger(__name__)

class OrderHandler(ConsumerHandler):
    """Smart handler with automatic method routing"""
    
    def __init__(self):
        # ✅ RECOMMENDED: Use dot notation for subjects
        subjects = [
            "orders.created",
            "orders.updated", 
            "orders.cancelled",
            "orders.shipped"
        ]
        super().__init__(subjects)

    async def handle_created(self, message):
        """Handles orders.created messages"""
        data = json.loads(message.data.decode())
        logger.info(f"New order created: {data}")

    async def handle_updated(self, message):
        """Handles orders.updated messages"""
        data = json.loads(message.data.decode())
        logger.info(f"Order updated: {data}")

    async def handle_cancelled(self, message):
        """Handles orders.cancelled messages"""
        data = json.loads(message.data.decode())
        logger.info(f"Order cancelled: {data}")

    async def handle_shipped(self, message):
        """Handles orders.shipped messages"""
        data = json.loads(message.data.decode())
        logger.info(f"Order shipped: {data}")

    async def fallback_handle(self, msg, reason="unknown"):
        """Custom fallback for unhandled messages"""
        data = json.loads(msg.data.decode())
        logger.error(f"Unhandled message for {msg.subject} (reason: {reason}): {data}")
        
        # Custom behavior: send to dead letter queue
        await self.send_to_dlq(msg, reason)
        await msg.ack()  # ACK after handling

class OrderConsumer(JetstreamPushConsumer):
    stream_name = "orders"
    subjects = ["orders.created", "orders.updated", "orders.cancelled", "orders.shipped"]
    
    # ✅ RECOMMENDED: Use wildcards for filtering
    filter_subject = "orders.*"  # Filter all order events
    
    # Retry configuration
    max_retries = 3
    initial_retry_delay = 1.0
    max_retry_delay = 60.0
    backoff_factor = 2.0
    
    # Error handling behavior
    handle_error_ack_behavior = ErrorAckBehavior.NAK

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.handler = OrderHandler()

    async def setup(self):
        return [
            operations.CreateStream(
                name=self.stream_name,
                subjects=self.subjects,
                storage="file"
            ),
        ]

    async def handle_message(self, message):
        """Route message to appropriate handler method"""
        await self.handler.handle(message)
    
    async def handle_error(self, message, error, attempt):
        """Optional: Custom error handling after max retries"""
        logger.error(f"Final error after {attempt} attempts: {error}")
```

### Pull Consumer with Subject Filtering
```python
from nats_consumer import JetstreamPullConsumer

class BatchOrderConsumer(JetstreamPullConsumer):
    stream_name = "orders"
    subjects = ["orders.created", "orders.updated", "orders.shipped"]
    
    # ✅ RECOMMENDED: Use wildcard or single subject filtering
    filter_subject = "orders.*"  # All order events
    # OR: filter_subject = "orders.created"  # Only creation events
    # OR: No filter_subject → automatically uses "orders.created" (subjects[0])
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.handler = OrderHandler()  # Reuse the same handler
    
    async def handle_message(self, message):
        """Route to handler for batch processing"""
        await self.handler.handle(message)
```

## Subject Filtering & Best Practices

### 🎯 Subject Naming (RECOMMENDED)
```python
# ✅ GOOD: Use dot notation for hierarchical subjects
subjects = [
    "orders.created",
    "orders.updated", 
    "orders.cancelled",
    "users.profile.updated",
    "payments.completed"
]

# ❌ AVOID: Mixed separators cause handler collisions
subjects = [
    "orders.created",    # → handle_created()
    "orders-created",    # → handle_created() ⚠️ COLLISION!
    "orders_created"     # → handle_created() ⚠️ COLLISION!
]
```

### 🎛️ Subject Filtering Strategies
```python
# Wildcard filtering (recommended for related events)
filter_subject = "orders.*"           # All order events
filter_subject = "users.profile.*"    # All profile events

# Single subject filtering (for specific processing)
filter_subject = "orders.created"     # Only creation events

# Pattern filtering (for complex hierarchies)
filter_subject = "*.error"           # All error events across domains
filter_subject = "orders.*.failed"   # All failed order operations

# No filtering (process everything)
filter_subject = ">"                 # All subjects in the stream

# Auto-filtering (if filter_subject not specified)
class MyConsumer(JetstreamPushConsumer):
    subjects = ["orders.created", "orders.updated"]
    # filter_subject automatically uses "orders.created" (subjects[0])
```

### 🔍 Collision Detection
The handler automatically detects and warns about subject collisions:
```python
# This will generate a warning:
class ProblematicHandler(ConsumerHandler):
    def __init__(self):
        subjects = [
            "orders.created",    # → handle_created()
            "users-created",     # → handle_created() ⚠️ COLLISION!
        ]
        super().__init__(subjects)
```

## Publishing Messages

**publish.py**
```python
import asyncio
import json
from nats_consumer import get_nats_client

async def publish_messages():
    ns = await get_nats_client()
    js = ns.jetstream()
    
    for i in range(5):
        data = {"id": i, "name": f"Order {i}", "status": "created"}
        data_b = json.dumps(data).encode("utf-8")
        print(f"Publishing message {i}...")
        await js.publish("orders.created", data_b)
    
    await ns.close()

if __name__ == "__main__":
    asyncio.run(publish_messages())
```

## Running Consumers

### Basic Usage
```bash
# Run a single consumer with setup
python manage.py nats_consumer OrderConsumer --setup

# Run multiple specific consumers
python manage.py nats_consumer OrderConsumer BatchOrderConsumer

# Run all registered consumers
python manage.py nats_consumer
```

### Development Options
```bash
# Enable auto-reload for development (watches for file changes)
python manage.py nats_consumer --reload

# Run with specific batch size for Pull consumers
python manage.py nats_consumer BatchOrderConsumer --batch-size 50
```

### Production Considerations
```bash
# Run with uvloop for better performance
python manage.py nats_consumer --event-loop uvloop

# Run with custom timeout
python manage.py nats_consumer --timeout 30
```

## Advanced Configuration

### Error Handling Behaviors
```python
from nats_consumer import ErrorAckBehavior

class MyConsumer(JetstreamPushConsumer):
    # Choose error acknowledgment behavior:
    handle_error_ack_behavior = ErrorAckBehavior.ACK  # Acknowledge and move on
    handle_error_ack_behavior = ErrorAckBehavior.NAK  # Negative ack for redelivery
    handle_error_ack_behavior = ErrorAckBehavior.IMPLEMENTED_BY_HANDLE_ERROR  # Custom handling
```

### Retry Configuration
```python
class MyConsumer(JetstreamPushConsumer):
    max_retries = 5  # Maximum retry attempts
    initial_retry_delay = 2.0  # Initial delay in seconds
    max_retry_delay = 120.0  # Maximum delay in seconds
    backoff_factor = 2.0  # Exponential backoff multiplier
```

### Performance Optimization

For production environments, uvloop provides better performance on Unix-like systems:

```bash
pip install django-nats-consumer[uvloop]
```

**settings.py**
```python
NATS_CONSUMER = {
    "event_loop_policy": "uvloop.EventLoopPolicy",
    "connect_args": {
        "servers": ["nats://localhost:4222"],
        "allow_reconnect": True,
        "max_reconnect_attempts": 10,
        "reconnect_time_wait": 2,
        "connect_timeout": 10,
    },
    "default_durable_name": "my-app",  # Default durable name for consumers
}
```

## Monitoring

Consumers provide built-in metrics:

```python
class MyConsumer(JetstreamPushConsumer):
    async def handle_message(self, message):
        # Access metrics
        print(f"Success count: {self.total_success_count}")
        print(f"Error count: {self.total_error_count}")
        print(f"Is running: {self.is_running}")
        print(f"Is connected: {self.is_connected}")
```

## Best Practices

### 📋 Subject Design
- **✅ Use dot notation**: `orders.created` instead of `orders-created` or `orders_created`
- **✅ Use hierarchical structure**: `users.profile.updated`, `orders.payment.completed`
- **✅ Use wildcards in filters**: `filter_subject = "orders.*"`
- **❌ Avoid mixed separators**: Don't mix `.`, `-`, and `_` in the same domain

### 🏗️ Consumer Architecture
- **Use Push consumers** for low-latency, event-driven processing
- **Use Pull consumers** for high-throughput batch processing
- **Use ConsumerHandler** for automatic message routing
- **Use subject filtering** to process only relevant events

### 🔧 Configuration
- **Configure appropriate retry policies** based on your use case
- **Implement proper error handling** with custom `handle_error` methods
- **Use durable consumers** in production for message persistence
- **Monitor consumer metrics** for operational insights

### 🎯 Handler Design
- **One handler method per event type**: `handle_created()`, `handle_updated()`
- **Use descriptive method names** that match your subject hierarchy
- **Validate handler implementations** with `validate_handlers()`
- **Implement fallback_handle()** for robust error handling

### 🛡️ Fallback Handling
```python
class RobustHandler(ConsumerHandler):
    async def fallback_handle(self, msg, reason="unknown"):
        """
        Custom fallback for unhandled messages.
        Default behavior: NAK (recommended for safety)
        
        Reasons:
        - "unhandled_subject": Subject not in handler's list
        - "no_mapping": No handler method mapping found  
        - "not_implemented": Handler method not implemented
        """
        if reason == "unhandled_subject":
            # Log and discard unknown subjects
            logger.warning(f"Unknown subject {msg.subject}, discarding")
            await msg.ack()
        else:
            # For implementation issues, NAK for redelivery
            logger.error(f"Handler issue for {msg.subject}: {reason}")
            await msg.nak()  # Default behavior

### 🎯 Filter Subject Examples
```python
# Explicit filtering (recommended)
class OrderConsumer(JetstreamPushConsumer):
    subjects = ["orders.created", "orders.updated", "orders.cancelled"]
    filter_subject = "orders.*"  # Process all order events

# Auto-filtering (uses subjects[0])
class SimpleConsumer(JetstreamPushConsumer):
    subjects = ["orders.created", "orders.updated"]
    # No filter_subject → automatically uses "orders.created"

# Single subject filtering
class CreationConsumer(JetstreamPushConsumer):
    subjects = ["orders.created", "orders.updated", "orders.cancelled"]
    filter_subject = "orders.created"  # Only creation events
```

## License

This project is licensed under the MIT License.

### Original Work Attribution

This project is a fork and significant enhancement of the original work by **Christian Toivola** ([@dev360](https://github.com/dev360)).

The original project was licensed under the BSD-3-Clause License. We gratefully acknowledge the foundational work that made this project possible.

**Original Author**: Christian Toivola  
**Original Repository**: https://github.com/dev360  
**Original License**: BSD-3-Clause

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
