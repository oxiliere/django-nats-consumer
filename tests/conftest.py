"""
Pytest configuration and fixtures for NATS consumer tests
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from nats.aio.msg import Msg
import json


@pytest.fixture
def mock_django_settings():
    """Mock Django settings for tests"""
    with patch('django.conf.settings') as mock_settings:
        mock_settings.NATS_CONSUMER = {
            "connect_args": {
                "servers": ["nats://localhost:4222"],
                "allow_reconnect": True,
                "max_reconnect_attempts": 5,
                "reconnect_time_wait": 1,
                "connect_timeout": 10,
            },
            "default_durable_name": "test-consumer",
        }
        yield mock_settings


@pytest.fixture
def mock_nats_client():
    """Mock NATS client for tests"""
    with patch('nats_consumer.client.get_nats_client') as mock_client:
        client = AsyncMock()
        client.is_connected = True
        client.jetstream.return_value = AsyncMock()
        mock_client.return_value = client
        yield client


@pytest.fixture
def mock_message():
    """Factory fixture for creating mock NATS messages"""
    def _create_message(subject: str, data: dict = None):
        msg = Mock(spec=Msg)
        msg.subject = subject
        msg.data = json.dumps(data or {}).encode()
        msg.ack = AsyncMock()
        msg.nak = AsyncMock()
        
        # Mock metadata for message tracking
        msg.metadata = Mock()
        msg.metadata.sequence = Mock()
        msg.metadata.sequence.stream = 1
        msg.metadata.sequence.consumer = 1
        
        return msg
    return _create_message


@pytest.fixture
def handler_subjects():
    """Standard test subjects for handlers"""
    return [
        "orders.created",       # Dot notation
        "orders-updated",       # Hyphen notation
        "orders_deleted",       # Underscore notation
        "payments",             # Single token
        "orders.old.archived",  # Multi-level
        "orders.*",             # Wildcard (should be ignored)
        "users.>",              # Wildcard (should be ignored)
    ]


@pytest.fixture
def integration_subjects():
    """Test subjects for integration tests"""
    return [
        "integration.created",
        "integration-updated",
        "integration_deleted"
    ]


@pytest.fixture
def mock_consumer_base():
    """Mock the base consumer functionality"""
    with patch('nats_consumer.consumer.NatsConsumerBase.__init__') as mock_init:
        mock_init.return_value = None
        yield mock_init
