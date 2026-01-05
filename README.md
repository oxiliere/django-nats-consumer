# django-nats-consumer
NATS + Django = ⚡️

A powerful Django integration for NATS JetStream with decorator-based message handlers, support for both Push and Pull consumers, native NATS retry mechanisms, and flexible wildcard subject routing.

## Features

- 🎯 **Decorator-Based Handlers**: Use `@handle` decorator for explicit, clean handler registration
- 🌟 **Wildcard Support**: Full support for `*` and `>` wildcards in subject patterns
- 🚀 **Push & Pull Consumers**: Support for both JetStream consumer types
- 🔄 **Native NATS Retry**: Built-in NATS retry with exponential backoff
- 🎛️ **Smart Routing**: Automatic message routing with exact and wildcard matching
- 🛡️ **Error Handling**: Configurable error acknowledgment behaviors
- 📊 **Monitoring**: Built-in success/error counters and logging
- ⚡ **Performance**: Optional uvloop support for better performance
- 🔧 **Django Integration**: Seamless integration with Django management commands
- 🧪 **Well Tested**: Comprehensive test suite with 52 passing tests
- 🔒 **Production Ready**: Used in production environments with robust error handling

## What's New

### Version 2.0 - Decorator-Based Handlers
- ✅ **`@handle` decorator** for explicit handler registration
- ✅ **Wildcard patterns** (`*` and `>`) fully supported
- ✅ **Multiple subjects per handler** - one method can handle multiple subjects
- ✅ **No naming conventions** - name your methods however you want
- ✅ **Native NATS retry** with exponential backoff
- ✅ **Cleaner API** - no more `__init__` with subjects list

## Installation

This library is in **Beta** status with comprehensive test coverage and production-ready features. The API is stable but may evolve based on community feedback.

```bash
# Install from PyPI
pip install oxnats
```

### Optional Performance Enhancement
```bash
# For better performance on Unix-like systems
pip install oxnats[uvloop]
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

## Subject Naming Convention (IMPORTANT)

**⚠️ STRONGLY RECOMMENDED: Use dot notation for all subjects**

NATS subjects should follow a hierarchical dot notation pattern:

```python
# ✅ RECOMMENDED: Dot notation (hierarchical)
'orders.created'
'orders.updated'
'users.profile.updated'
'payments.completed'
'notifications.email.sent'

# ❌ NOT RECOMMENDED: Other separators
'orders-created'      # Hyphen separator
'orders_created'      # Underscore separator
'orderscreated'       # No separator
```

**Why dot notation?**
- ✅ **Standard NATS convention** - Industry best practice
- ✅ **Wildcard support** - Works seamlessly with `*` and `>` wildcards
- ✅ **Hierarchical clarity** - Clear domain.entity.action structure
- ✅ **Better routing** - Easier to filter and route messages
- ✅ **Consistency** - Matches NATS ecosystem patterns

**Examples of good subject hierarchies:**
```python
# E-commerce domain
'orders.created'
'orders.updated'
'orders.payment.completed'
'orders.shipment.dispatched'

# User management
'users.registered'
'users.profile.updated'
'users.password.reset'

# Notifications
'notifications.email.sent'
'notifications.sms.sent'
'notifications.push.delivered'
```

## Quick Start

### 1. Define Your Handler with `@handle` Decorator

```python
# {app_name}/consumers.py
from nats_consumer import ConsumerHandler, handle
import logging
import json

logger = logging.getLogger(__name__)

class OrderHandler(ConsumerHandler):
    """Handler using @handle decorator for explicit registration"""
    
    @handle('orders.created')
    async def on_order_created(self, message):
        """Handle new order creation"""
        data = json.loads(message.data.decode())
        logger.info(f"New order created: {data}")
    
    @handle('orders.updated', 'orders.modified')
    async def on_order_changed(self, message):
        """Handle order updates - multiple subjects, one handler!"""
        data = json.loads(message.data.decode())
        logger.info(f"Order changed: {data}")
    
    @handle('orders.cancelled')
    async def on_order_cancelled(self, message):
        """Handle order cancellation"""
        data = json.loads(message.data.decode())
        logger.info(f"Order cancelled: {data}")
    
    @handle('orders.*')  # Wildcard support!
    async def on_any_order_event(self, message):
        """Catch-all for any order event"""
        logger.debug(f"Order event: {message.subject}")
    
    async def fallback_handle(self, msg, reason="unknown"):
        """Custom fallback for unhandled messages"""
        logger.error(f"Unhandled: {msg.subject} (reason: {reason})")
        await msg.nak()  # NAK for redelivery (default behavior)

### 2. Create Your Consumer

```python
from nats_consumer import JetstreamPushConsumer, operations, ErrorAckBehavior
from nats_consumer.operations import api

class OrderConsumer(JetstreamPushConsumer):
    stream_name = "orders"
    subjects = ["orders.created", "orders.updated", "orders.cancelled"]
    
    # Native NATS retry configuration
    max_deliver = 3  # Max delivery attempts
    ack_wait = 30  # Seconds to wait for ACK
    backoff_delays = [1.0, 5.0, 10.0]  # Exponential backoff delays
    
    # Error handling behavior after max retries
    handle_error_ack_behavior = ErrorAckBehavior.NAK

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.handler = OrderHandler()

    async def setup(self):
        """Setup stream before starting consumer"""
        return [
            # ✅ PRODUCTION: Use CreateOrUpdateStream for flexibility
            # Automatically updates stream config when it changes
            operations.CreateOrUpdateStream(
                name=self.stream_name,
                subjects=self.subjects,
                retention=api.RetentionPolicy.LIMITS,
                max_age=3600,  # 1 hour retention
            ),
        ]

    async def handle_message(self, message):
        """Route message to handler"""
        await self.handler.handle(message)
    
    async def handle_error(self, message, error, delivery_count):
        """Called when max_deliver is reached"""
        logger.error(f"Max retries reached after {delivery_count} attempts: {error}")
        # Send to DLQ, alert monitoring, etc.
```

### 3. Run Your Consumer

```bash
# Setup stream and start consumer
python manage.py nats_consumer OrderConsumer --setup

# Development mode with auto-reload
python manage.py nats_consumer OrderConsumer --reload
```

### 💡 Production Best Practice: Stream Setup

**Use `CreateOrUpdateStream` instead of `CreateStream` in production:**

```python
# ⚠️ CreateStream - Only creates, doesn't update
async def setup(self):
    return [
        operations.CreateStream(
            name=self.stream_name,
            subjects=self.subjects,
        ),
    ]
    # If stream exists: logs warning, doesn't update configuration
    # If stream missing: creates it

# ✅ CreateOrUpdateStream - Creates OR updates (RECOMMENDED)
async def setup(self):
    return [
        operations.CreateOrUpdateStream(
            name=self.stream_name,
            subjects=self.subjects,
            retention=api.RetentionPolicy.LIMITS,
            max_age=3600,
        ),
    ]
    # If stream exists: updates configuration
    # If stream missing: creates it
```

**Why `CreateOrUpdateStream` for production?**
- ✅ **Flexible** - Updates stream configuration when it changes
- ✅ **Idempotent** - Safe to run multiple times
- ✅ **CI/CD friendly** - Applies configuration changes automatically
- ✅ **Zero downtime** - Updates streams without recreation
- ✅ **Version control** - Stream config evolves with your code

**When to use each:**
```python
# CreateStream - Simple cases
# - Only creates stream if missing
# - Logs warning if stream exists (doesn't update)
# - Good for static configurations that never change

# CreateOrUpdateStream - Production (RECOMMENDED)
# - Creates stream if missing
# - Updates stream configuration if exists
# - Perfect when stream config evolves over time
# - Ideal for CI/CD pipelines

# DeleteStream - Maintenance only
# - Use nats_delete_stream command
# - Requires confirmation

# UpdateStream - Manual updates only  
# - Use nats_update_stream command
# - For specific one-time configuration changes
```
```

## Key Features Explained

### 🎯 Decorator-Based Handler Registration

The `@handle` decorator provides explicit, clean handler registration:

```python
from nats_consumer import ConsumerHandler, handle

class MyHandler(ConsumerHandler):
    # ✅ One subject, one handler
    @handle('orders.created')
    async def on_created(self, msg):
        pass
    
    # ✅ Multiple subjects, one handler
    @handle('orders.updated', 'orders.modified', 'orders.changed')
    async def on_updated(self, msg):
        pass
    
    # ✅ Wildcard patterns
    @handle('orders.*')  # Match orders.created, orders.updated, etc.
    async def on_any_order(self, msg):
        pass
    
    @handle('notifications.>')  # Match notifications.email, notifications.sms.sent, etc.
    async def on_any_notification(self, msg):
        pass
    
    # ✅ Name methods however you want!
    @handle('payments.completed')
    async def process_payment_completion(self, msg):
        pass
```

**Benefits:**
- **Explicit**: Clear which methods handle which subjects
- **Flexible**: One method can handle multiple subjects
- **No conventions**: Name methods however you want
- **Wildcards**: Full support for `*` and `>` patterns
- **Type-safe**: Easy to understand and maintain

### 🔄 Native NATS Retry Mechanism

Uses NATS JetStream's built-in retry with exponential backoff:

```python
class MyConsumer(JetstreamPushConsumer):
    max_deliver = 5  # Maximum delivery attempts
    ack_wait = 30  # Seconds to wait for ACK before retry
    backoff_delays = [1.0, 2.0, 4.0, 8.0, 16.0]  # Exponential backoff
```

**How it works:**
1. Message fails → NAK sent to NATS
2. NATS waits `backoff_delays[attempt]` seconds
3. NATS redelivers message
4. After `max_deliver` attempts → `handle_error()` called

### 🌟 Wildcard Subject Matching

**Exact match takes priority:**
```python
class MyHandler(ConsumerHandler):
    @handle('orders.created')  # Exact match
    async def on_created(self, msg):
        # This is called for orders.created
        pass
    
    @handle('orders.*')  # Wildcard
    async def on_any_order(self, msg):
        # This is called for orders.updated, orders.deleted, etc.
        # But NOT for orders.created (exact match wins)
        pass
```

**Wildcard patterns:**
- `*` - Matches exactly one token: `orders.*` matches `orders.created` but not `orders.payment.completed`
- `>` - Matches one or more tokens: `orders.>` matches `orders.created` and `orders.payment.completed`

## Consumer Types

### Push Consumer (Event-Driven)

Best for low-latency, real-time event processing:

```python
from nats_consumer import JetstreamPushConsumer
from nats_consumer.operations import CreateOrUpdateStream, api

class RealtimeOrderConsumer(JetstreamPushConsumer):
    stream_name = "orders"
    subjects = ["orders.*"]  # All order events
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.handler = OrderHandler()
    
    async def setup(self):
        """Use CreateOrUpdateStream for production"""
        return [
            CreateOrUpdateStream(
                name=self.stream_name,
                subjects=self.subjects,
                retention=api.RetentionPolicy.LIMITS,
            ),
        ]
    
    async def handle_message(self, message):
        await self.handler.handle(message)
```

### Pull Consumer (Batch Processing)

Best for high-throughput batch processing:

```python
from nats_consumer import JetstreamPullConsumer
from nats_consumer.operations import CreateOrUpdateStream, api

class BatchOrderConsumer(JetstreamPullConsumer):
    stream_name = "orders"
    subjects = ["orders.*"]
    batch_size = 100  # Process 100 messages at a time
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.handler = OrderHandler()
    
    async def setup(self):
        """Use CreateOrUpdateStream for production"""
        return [
            CreateOrUpdateStream(
                name=self.stream_name,
                subjects=self.subjects,
                retention=api.RetentionPolicy.LIMITS,
            ),
        ]
    
    async def handle_message(self, message):
        await self.handler.handle(message)
```

## Advanced Patterns

### Multiple Handlers for Different Concerns

```python
class OrderValidationHandler(ConsumerHandler):
    @handle('orders.created')
    async def validate_order(self, msg):
        # Validation logic
        pass

class OrderNotificationHandler(ConsumerHandler):
    @handle('orders.created', 'orders.updated')
    async def send_notification(self, msg):
        # Notification logic
        pass

class OrderConsumer(JetstreamPushConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.validation_handler = OrderValidationHandler()
        self.notification_handler = OrderNotificationHandler()
    
    async def handle_message(self, message):
        # Chain handlers
        await self.validation_handler.handle(message)
        await self.notification_handler.handle(message)
```

### Custom Fallback Handling

```python
class RobustHandler(ConsumerHandler):
    @handle('orders.created')
    async def on_created(self, msg):
        pass
    
    async def fallback_handle(self, msg, reason="unknown"):
        """
        Called when no handler matches the subject.
        
        Reasons:
        - "no_handler": No handler registered for this subject
        
        Default behavior: NAK (message will be redelivered)
        """
        if reason == "no_handler":
            # Log and discard unknown subjects
            logger.warning(f"Unknown subject: {msg.subject}")
            await msg.ack()  # ACK to prevent redelivery
        else:
            # NAK for potential retry
            logger.error(f"Handler issue: {msg.subject} ({reason})")
            await msg.nak()
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
    
    # ✅ ALWAYS use dot notation for subjects
    for i in range(5):
        data = {"id": i, "name": f"Order {i}", "status": "created"}
        data_b = json.dumps(data).encode("utf-8")
        print(f"Publishing message {i}...")
        
        # ✅ Good: dot notation
        await js.publish("orders.created", data_b)
        
        # ❌ Bad: other separators
        # await js.publish("orders-created", data_b)  # DON'T DO THIS
        # await js.publish("orders_created", data_b)  # DON'T DO THIS
    
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

### 📋 Handler Design

**✅ DO:**
- Use `@handle` decorator for all handlers
- Use descriptive method names (no naming conventions required)
- Implement `fallback_handle()` for unhandled messages
- Use wildcards for catch-all handlers
- Handle one concern per handler class

**❌ DON'T:**
- Don't forget to call `super().__init__()` in your handler
- Don't register the same subject in multiple handlers (causes warnings)
- Don't mix handler logic with consumer logic

### 🎯 Subject Design

**✅ ALWAYS DO:**
- **Use dot notation exclusively**: `orders.created`, `users.profile.updated`
- **Use hierarchical structure**: `domain.entity.action` or `domain.action`
- **Use lowercase**: `orders.created` not `Orders.Created`
- **Use descriptive names**: `orders.payment.completed` not `orders.pc`
- **Use wildcards strategically**: `orders.*`, `notifications.>`

**❌ NEVER DO:**
- **Don't use hyphens**: ❌ `orders-created` → ✅ `orders.created`
- **Don't use underscores**: ❌ `orders_created` → ✅ `orders.created`
- **Don't mix separators**: ❌ `orders.created` + `users-updated`
- **Don't use overly deep hierarchies**: ❌ `a.b.c.d.e.f.g` (max 3-4 levels)
- **Don't use spaces or special chars**: ❌ `orders created` or `orders@created`

**Subject naming patterns:**
```python
# Pattern 1: domain.action (simple)
'orders.created'
'payments.completed'
'users.registered'

# Pattern 2: domain.entity.action (detailed)
'orders.payment.completed'
'users.profile.updated'
'notifications.email.sent'

# Pattern 3: domain.subdomain.entity.action (complex)
'ecommerce.orders.payment.completed'
'platform.users.profile.updated'
```

### 🔧 Retry Configuration

```python
class MyConsumer(JetstreamPushConsumer):
    # Conservative (for critical operations)
    max_deliver = 10
    ack_wait = 60
    backoff_delays = [1, 2, 5, 10, 30, 60, 120, 300, 600, 900]
    
    # Aggressive (for non-critical operations)
    max_deliver = 3
    ack_wait = 10
    backoff_delays = [1, 5, 10]
```

### 🛡️ Error Handling

```python
from nats_consumer import ErrorAckBehavior

class MyConsumer(JetstreamPushConsumer):
    # After max_deliver is reached:
    
    # Option 1: NAK (redelivery - default, safest)
    handle_error_ack_behavior = ErrorAckBehavior.NAK
    
    # Option 2: ACK (discard message)
    handle_error_ack_behavior = ErrorAckBehavior.ACK
    
    # Option 3: Custom (handle in handle_error method)
    handle_error_ack_behavior = ErrorAckBehavior.IMPLEMENTED_BY_HANDLE_ERROR
    
    async def handle_error(self, msg, error, delivery_count):
        # Send to DLQ, alert monitoring, etc.
        await send_to_dlq(msg, error)
        await msg.ack()  # Must ACK/NAK if using IMPLEMENTED_BY_HANDLE_ERROR
```

### 📊 Monitoring

```python
class MonitoredConsumer(JetstreamPushConsumer):
    async def handle_message(self, message):
        # Built-in metrics
        logger.info(f"Success: {self.total_success_count}")
        logger.info(f"Errors: {self.total_error_count}")
        logger.info(f"Running: {self.is_running}")
        logger.info(f"Connected: {self.is_connected}")
        
        await self.handler.handle(message)
```

## Migration from v1.x

If you're upgrading from the old auto-detection approach, see [DECORATOR_MIGRATION.md](DECORATOR_MIGRATION.md) for a complete migration guide.

**Quick summary:**

```python
# OLD (v1.x)
class OrderHandler(ConsumerHandler):
    def __init__(self):
        subjects = ["orders.created", "orders.updated"]  # ✅ Good: dot notation
        super().__init__(subjects)
    
    async def handle_created(self, msg):  # Auto-detected by name
        pass

# NEW (v2.x)
class OrderHandler(ConsumerHandler):
    @handle('orders.created')  # ✅ Explicit with decorator + dot notation
    async def on_created(self, msg):  # Name it however you want!
        pass
    
    @handle('orders.updated', 'orders.modified')  # Multiple subjects!
    async def on_updated(self, msg):
        pass
```

**⚠️ Important: If migrating from non-dot notation subjects**

If your old code used hyphens or underscores, **strongly consider migrating to dot notation**:

```python
# OLD (BAD PRACTICE)
subjects = ["orders-created", "orders_updated"]  # ❌ Don't do this

# NEW (BEST PRACTICE)
subjects = ["orders.created", "orders.updated"]  # ✅ Always use dots
```

This may require updating your publishers and stream configurations, but it's worth it for long-term maintainability.

## Testing

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_handler.py -v

# Run with coverage
uv run pytest --cov=nats_consumer --cov-report=html
```

## Performance

For production environments, install with uvloop for better performance:

```bash
pip install oxnats[uvloop]
```

**settings.py:**
```python
NATS_CONSUMER = {
    "event_loop_policy": "uvloop.EventLoopPolicy",
    "connect_args": {
        "servers": ["nats://localhost:4222"],
        "allow_reconnect": True,
        "max_reconnect_attempts": 10,
    },
}
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

## Support

For issues, questions, or contributions, please visit the [GitHub repository](https://github.com/yourusername/django-nats-consumer).
