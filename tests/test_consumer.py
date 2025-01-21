from unittest.mock import AsyncMock, patch

import pytest

from nats_consumer.consumer import validate_stream_name


@pytest.fixture
def mock_nats_client():
    with patch("nats_consumer.consumer.NATS") as mock_nats:
        client = AsyncMock()
        client.is_connected = True
        mock_nats.return_value = client
        yield client


@pytest.fixture
def mock_jetstream():
    return AsyncMock()


class TestConsumerBase:
    def test_validate_stream_name(self):
        # Test valid stream names
        assert validate_stream_name("valid_stream") == "valid_stream"

        # Test invalid stream names
        with pytest.raises(ValueError):
            validate_stream_name("invalid stream")
        with pytest.raises(ValueError):
            validate_stream_name("invalid.stream")

    def test_consumer_meta(self):
        pass
