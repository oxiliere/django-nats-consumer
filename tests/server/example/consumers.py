import json
import logging
from nats_consumer import JetstreamPullConsumer, JetstreamPushConsumer, operations
from nats_consumer.operations import api
from nats_consumer.handler import ConsumerHandler

logger = logging.getLogger(__name__)


class ExampleHandler(ConsumerHandler):
    """Example handler for testing different subject formats"""
    
    def __init__(self):
        subjects = [
            "example.created",      # Dot notation
            "example-updated",      # Hyphen notation  
            "example_deleted",      # Underscore notation
            "notifications",        # Single token
            "example.old.archived", # Multi-level
        ]
        super().__init__(subjects)

    async def handle_created(self, msg):
        """Handle example.created messages"""
        data = json.loads(msg.data.decode())
        logger.info(f"Created: {data}")

    async def handle_updated(self, msg):
        """Handle example-updated messages"""
        data = json.loads(msg.data.decode())
        logger.info(f"Updated: {data}")

    async def handle_deleted(self, msg):
        """Handle example_deleted messages"""
        data = json.loads(msg.data.decode())
        logger.info(f"Deleted: {data}")

    async def handle_notifications(self, msg):
        """Handle notifications messages"""
        data = json.loads(msg.data.decode())
        logger.info(f"Notification: {data}")

    async def handle_old_archived(self, msg):
        """Handle example.old.archived messages"""
        data = json.loads(msg.data.decode())
        logger.info(f"Archived: {data}")


class ExamplePullConsumer(JetstreamPullConsumer):
    stream_name = "example_pull"
    subjects = [
        "example.created",
        "example-updated", 
        "example_deleted",
        "notifications",
        "example.old.archived"
    ]

    filter_subject = "example.*"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.handler = ExampleHandler()

    def setup(self):
        return [
            operations.CreateStream(
                name=self.stream_name,
                subjects=self.subjects,
                retention=api.RetentionPolicy.LIMITED_TIME,
                max_age=1000,
            )
        ]

    async def handle_message(self, message):
        """Route message to appropriate handler"""
        await self.handler.handle(message)


class ExamplePushConsumer(JetstreamPushConsumer):
    stream_name = "example_push"
    subjects = [
        "example.created",
        "example-updated",
        "example_deleted", 
        "notifications",
        "example.old.archived"
    ]

    filter_subject = "example.*"

    
    # Test retry configuration
    max_retries = 2
    initial_retry_delay = 0.5
    max_retry_delay = 5.0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.handler = ExampleHandler()

    def setup(self):
        return [
            operations.CreateStream(
                name=self.stream_name,
                subjects=self.subjects,
                retention=api.RetentionPolicy.LIMITED_TIME,
                max_age=1000,
            )
        ]

    async def handle_message(self, message):
        """Route message to appropriate handler"""
        await self.handler.handle(message)

    async def handle_error(self, message, error, attempt):
        """Custom error handling for testing"""
        logger.error(f"Test error handling - attempt {attempt}: {error}")


class LegacyConsumer(JetstreamPushConsumer):
    """Legacy consumer without handler for backward compatibility testing"""
    stream_name = "legacy"
    subjects = ["legacy.test"]

    def setup(self):
        return [
            operations.CreateStream(
                name=self.stream_name,
                subjects=self.subjects,
                retention=api.RetentionPolicy.LIMITED_TIME,
                max_age=1000,
            )
        ]

    async def handle_message(self, message):
        """Direct message handling without handler"""
        data = json.loads(message.data.decode())
        logger.info(f"Legacy handling: {data}")
