import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from nats_consumer.consumer import ErrorAckBehavior, JetstreamPushConsumer, validate_stream_name


@pytest.fixture
def mock_nats_client():
    with patch("nats_consumer.consumer.NATS") as mock_nats:
        client = AsyncMock()
        client.is_connected = True
        mock_nats.return_value = client
        yield client


@pytest.fixture
def mock_jetstream():
    mock_jetstream = Mock(subscribe=AsyncMock(), consumer_info=AsyncMock())
    return mock_jetstream


class ErrorConsumer(JetstreamPushConsumer):
    stream_name = "test_stream"
    subjects = ["test.subject"]

    max_retries = 3
    initial_retry_delay = 0.01

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_success_count = 0
        self.test_error_count = 0

    async def handle_message(self, msg):
        if msg.data["id"] == 1:
            self.test_error_count += 1
            raise ValueError("Simulated error for message 1")

        self.test_success_count += 1
        return


class HandledErrorConsumer(JetstreamPushConsumer):
    stream_name = "test_stream"
    subjects = ["test.subject"]

    max_retries = 1
    initial_retry_delay = 0.01

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_success_count = 0
        self.test_error_count = 0

    async def handle_message(self, msg):
        if msg.data["id"] == 1:
            self.test_error_count += 1
            raise ValueError("Simulated error for message 1")

        self.test_success_count += 1
        return

    async def handle_error(self, msg, last_error, retry_count):
        pass


@pytest.fixture
def consumer(mock_nats_client, mock_jetstream):
    consumer = ErrorConsumer(nats_client=mock_nats_client)
    consumer._nats_client.jetstream.return_value = mock_jetstream
    return consumer


def create_mock_msg(stream_seq=1, num_delivered=1, msg_id=1):
    """Helper to create properly configured mock messages"""
    msg = AsyncMock()
    msg.metadata.stream_seq = stream_seq
    msg.metadata.num_delivered = num_delivered
    # Create a proper mock that allows dictionary access
    msg.data = {"id": msg_id}
    msg.ack = AsyncMock()
    msg.nak = AsyncMock()
    # Ensure _ackd is not set
    if hasattr(msg, '_ackd'):
        delattr(msg, '_ackd')
    return msg


@pytest.fixture
def mock_msg():
    return create_mock_msg()


class TestConsumerBase:
    def test_validate_stream_name(self):
        # Test valid stream names
        assert validate_stream_name("valid_stream") == "valid_stream"

        # Test invalid stream names
        with pytest.raises(ValueError):
            validate_stream_name("invalid stream")
        with pytest.raises(ValueError):
            validate_stream_name("invalid.stream")

    @pytest.mark.asyncio
    async def test_custom_error_handling(self, consumer, mock_msg):
        # Mock the setup_subscriptions to avoid real NATS interaction
        consumer.setup_subscriptions = AsyncMock()

        # Mock the message handling
        mock_msg_1 = create_mock_msg(stream_seq=1, num_delivered=1, msg_id=1)
        mock_msg_2 = create_mock_msg(stream_seq=2, num_delivered=1, msg_id=2)
        mock_msg_3 = create_mock_msg(stream_seq=3, num_delivered=1, msg_id=3)

        # With native NATS retry, first error triggers NAK (not max_deliver yet)
        await consumer.wrap_handle_message(mock_msg_1)
        await consumer.wrap_handle_message(mock_msg_2)
        await consumer.wrap_handle_message(mock_msg_3)

        # msg_1 fails once and gets NAKed (NATS will redeliver)
        assert consumer.test_error_count == 1
        assert consumer.total_success_count == 2
        assert consumer.total_error_count == 0  # Not at max_deliver yet

        # Assert that ack and nak were called correctly
        mock_msg_1.nak.assert_called_once()  # NAKed for redelivery
        mock_msg_1.ack.assert_not_called()
        mock_msg_2.ack.assert_called_once()
        mock_msg_2.nak.assert_not_called()
        mock_msg_3.ack.assert_called_once()
        mock_msg_3.nak.assert_not_called()

    @pytest.mark.asyncio
    async def test_exponential_retry(self, consumer, mock_msg):
        # Test native NATS retry with backoff configuration
        # Simulate message at max_deliver to trigger error handling
        mock_msg.metadata.num_delivered = consumer.max_deliver
        
        # Mock handle_error to verify it's called
        consumer.handle_error = AsyncMock()
        
        await consumer.wrap_handle_message(mock_msg)
        
        # At max_deliver, handle_error should be called
        consumer.handle_error.assert_called_once()
        # Message should be NAKed (default behavior)
        mock_msg.nak.assert_called_once()
        assert consumer.total_error_count == 1

    @pytest.mark.asyncio
    async def test_execution_order(self, consumer, mock_msg):
        # Mock the setup_subscriptions to avoid real NATS interaction
        consumer.setup_subscriptions = AsyncMock()

        # Mock the message handling
        mock_msg_1 = create_mock_msg(stream_seq=1, num_delivered=1, msg_id=1)
        mock_msg_2 = create_mock_msg(stream_seq=2, num_delivered=1, msg_id=2)
        mock_msg_3 = create_mock_msg(stream_seq=3, num_delivered=1, msg_id=3)

        # Initialize events list to track processing order
        consumer.events = []

        async def track_order(msg):
            consumer.events.append(msg.metadata.stream_seq)
            if msg.data["id"] == 1:
                await asyncio.sleep(1)
                raise ValueError("Simulated error for message 1")

        consumer.handle_message = track_order

        sleep_mock = AsyncMock(new_callable=AsyncMock)
        with patch("asyncio.sleep", sleep_mock):
            # Simulate message processing
            await consumer.wrap_handle_message(mock_msg_1)
            await consumer.wrap_handle_message(mock_msg_2)
            await consumer.wrap_handle_message(mock_msg_3)

        # With native retry, msg_1 fails once and gets NAKed
        # No custom retry loop, so only one attempt per call
        assert consumer.events == [1, 2, 3]
        mock_msg_1.nak.assert_called_once()
        mock_msg_2.ack.assert_called_once()
        mock_msg_3.ack.assert_called_once()

    @pytest.mark.asyncio
    async def test_message_tracking_cleanup(self, consumer, mock_msg):
        # Test successful handling with native retry (no custom tracking)
        async def successful_handler(msg):
            pass

        consumer.handle_message = successful_handler

        await consumer.wrap_handle_message(mock_msg)

        # Native retry doesn't use custom tracking
        assert consumer.total_success_count == 1
        mock_msg.ack.assert_called_once()

    @pytest.mark.asyncio
    async def test_message_tracking_cleanup_after_max_retries(self, consumer, mock_msg):
        # Test behavior when max_deliver is reached
        mock_msg.metadata.num_delivered = consumer.max_deliver
        consumer.handle_error = AsyncMock()

        await consumer.wrap_handle_message(mock_msg)

        # At max_deliver, error should be counted and handle_error called
        assert consumer.total_error_count == 1
        consumer.handle_error.assert_called_once()
        mock_msg.nak.assert_called_once()  # Default behavior

    @pytest.mark.asyncio
    async def test_real_execution_order(self, consumer, mock_nats_client):
        # Allow setup_subscriptions to execute
        mock_jetstream = mock_nats_client.jetstream.return_value

        # Mock the subscription object
        mock_sub = AsyncMock()
        mock_sub.callback = consumer.wrap_handle_message

        # Ensure js.subscribe returns the mock_sub
        mock_jetstream.subscribe.return_value = mock_sub

        # Mock messages
        mock_msg_1 = create_mock_msg(stream_seq=1, num_delivered=1, msg_id=1)
        mock_msg_2 = create_mock_msg(stream_seq=2, num_delivered=1, msg_id=2)
        mock_msg_3 = create_mock_msg(stream_seq=3, num_delivered=1, msg_id=3)

        # Initialize events list to track processing order
        consumer.events = []

        async def track_order(msg):
            consumer.events.append(msg.metadata.stream_seq)
            if msg.data["id"] == 1:
                await asyncio.sleep(1)
                raise ValueError("Simulated error for message 1")

        consumer.handle_message = track_order

        with patch("asyncio.sleep", AsyncMock()):
            # Simulate the callback invocation
            async def simulate_message_processing():
                await mock_sub.callback(mock_msg_2)
                await mock_sub.callback(mock_msg_3)
                await mock_sub.callback(mock_msg_1)

            # Run the simulation and stop after processing 6 events
            await asyncio.wait_for(simulate_message_processing(), timeout=5)

        # With native retry, no custom retry loop - just one attempt per message
        assert consumer.events == [2, 3, 1]
        mock_msg_1.nak.assert_called_once()
        mock_msg_2.ack.assert_called_once()
        mock_msg_3.ack.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_error_callback(self, consumer, mock_msg):
        # Mock the setup_subscriptions to avoid real NATS interaction
        consumer.setup_subscriptions = AsyncMock()
        # Mock the message handling
        mock_msg = create_mock_msg(stream_seq=1, num_delivered=consumer.max_deliver, msg_id=1)
        # Track if handle_error was called
        consumer.handle_error = AsyncMock()
        
        await consumer.wrap_handle_message(mock_msg)
        
        # Verify handle_error was called at max_deliver
        consumer.handle_error.assert_called_once()
        # Ensure correct default ack/nak behavior
        mock_msg.ack.assert_not_called()
        mock_msg.nak.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_error_ack_behavior_nak(self, consumer, mock_msg):
        # Set behavior to Nak
        consumer.setup_subscriptions = AsyncMock()
        consumer.handle_error = AsyncMock()
        mock_msg = create_mock_msg(num_delivered=consumer.max_deliver)

        await consumer.wrap_handle_message(mock_msg)

        # Verify NAK was called at max_deliver
        mock_msg.nak.assert_called_once()
        mock_msg.ack.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_error_ack_behavior_ack(self, consumer, mock_msg):
        # Set behavior to Ack
        consumer.handle_error_ack_behavior = ErrorAckBehavior.ACK
        consumer.setup_subscriptions = AsyncMock()
        consumer.handle_error = AsyncMock()
        mock_msg = create_mock_msg(num_delivered=consumer.max_deliver)

        await consumer.wrap_handle_message(mock_msg)

        # Verify ACK was called at max_deliver
        mock_msg.ack.assert_called_once()
        mock_msg.nak.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_error_ack_behavior_implemented_by_handle_error(self, consumer, mock_msg):
        # Set behavior to ImplementedByHandleError
        consumer.handle_error_ack_behavior = ErrorAckBehavior.IMPLEMENTED_BY_HANDLE_ERROR
        consumer.setup_subscriptions = AsyncMock()
        consumer.handle_error = AsyncMock()
        mock_msg = create_mock_msg(num_delivered=consumer.max_deliver)

        await consumer.wrap_handle_message(mock_msg)

        # Verify neither ACK nor NAK was called (handled by handle_error)
        mock_msg.ack.assert_not_called()
        mock_msg.nak.assert_not_called()
        consumer.handle_error.assert_called_once()


class TestDurableName:
    def test_get_durable_name_fallback(self, consumer):
        # Test fallback to default durable name
        assert consumer.get_durable_name() == "default"
        assert consumer.deliver_subject == "default.deliver"

        # Test using a custom durable name
        consumer.durable_name = "custom_durable"
        assert consumer.get_durable_name() == "custom_durable"
        assert consumer.deliver_subject == "custom_durable.deliver"
