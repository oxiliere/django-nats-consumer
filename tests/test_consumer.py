import asyncio
from unittest.mock import ANY, AsyncMock, Mock, patch

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


@pytest.fixture
def mock_msg():
    msg = AsyncMock()
    msg.metadata.stream_seq = 1
    msg.data = {"id": 1}
    return msg


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
        mock_msg_1 = AsyncMock()
        mock_msg_1.metadata.stream_seq = 1
        mock_msg_1.data = {"id": 1}
        mock_msg_1.ack = AsyncMock()
        mock_msg_1.nak = AsyncMock()

        mock_msg_2 = AsyncMock()
        mock_msg_2.metadata.stream_seq = 2
        mock_msg_2.data = {"id": 2}
        mock_msg_2.ack = AsyncMock()
        mock_msg_2.nak = AsyncMock()

        mock_msg_3 = AsyncMock()
        mock_msg_3.metadata.stream_seq = 3
        mock_msg_3.data = {"id": 3}
        mock_msg_3.ack = AsyncMock()
        mock_msg_3.nak = AsyncMock()

        # This makes the tests run faster.. the sleep doesn't
        # affect the test results or order of execution
        with patch("asyncio.sleep", AsyncMock()):
            await consumer.wrap_handle_message(mock_msg_1)
            await consumer.wrap_handle_message(mock_msg_2)
            await consumer.wrap_handle_message(mock_msg_3)

        # It should fail first time, then retry 3 times, then succeed
        assert consumer.test_error_count == 4
        assert consumer.total_success_count == 2

        # The reporting should be just 1 error
        assert consumer.total_error_count == 1

        # Assert that ack and nak were called correctly
        mock_msg_1.nak.assert_called()
        mock_msg_1.ack.assert_not_called()
        mock_msg_2.ack.assert_called_once()
        mock_msg_2.nak.assert_not_called()
        mock_msg_3.ack.assert_called_once()
        mock_msg_3.nak.assert_not_called()

    @pytest.mark.asyncio
    async def test_exponential_retry(self, consumer, mock_msg):
        # Mock asyncio.sleep to capture delay values
        sleep_mock = AsyncMock(new_callable=AsyncMock)
        with patch("asyncio.sleep", sleep_mock):
            # Simulate message processing with retries
            await consumer.wrap_handle_message(mock_msg)

            # Calculate expected delays
            expected_delays = [
                consumer.initial_retry_delay * (consumer.backoff_factor**i) for i in range(consumer.max_retries)
            ]

            # Assert that asyncio.sleep was called with the expected delays
            actual_delays = [call.args[0] for call in sleep_mock.call_args_list]
            assert actual_delays == expected_delays
            assert actual_delays == [0.01, 0.02, 0.04]

    @pytest.mark.asyncio
    async def test_execution_order(self, consumer, mock_msg):
        # Mock the setup_subscriptions to avoid real NATS interaction
        consumer.setup_subscriptions = AsyncMock()

        # Mock the message handling
        mock_msg_1 = AsyncMock()
        mock_msg_1.metadata.stream_seq = 1
        mock_msg_1.data = {"id": 1}

        mock_msg_2 = AsyncMock()
        mock_msg_2.metadata.stream_seq = 2
        mock_msg_2.data = {"id": 2}

        mock_msg_3 = AsyncMock()
        mock_msg_3.metadata.stream_seq = 3
        mock_msg_3.data = {"id": 3}

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

        # Assert the order of execution
        # This is not what I had expected, but it is what I got:
        # .. I had expected
        assert consumer.events == [1, 1, 1, 1, 2, 3]

    @pytest.mark.asyncio
    async def test_message_tracking_cleanup(self, consumer, mock_msg):
        # Test successful handling cleans up tracking
        async def successful_handler(msg):
            pass

        consumer.handle_message = successful_handler

        await consumer.wrap_handle_message(mock_msg)

        assert mock_msg.metadata.stream_seq not in consumer._message_attempts
        assert mock_msg.metadata.stream_seq not in consumer._retry_tasks
        assert consumer.total_success_count == 1

    @pytest.mark.asyncio
    async def test_message_tracking_cleanup_after_max_retries(self, consumer, mock_msg):
        # Force max retries to be exceeded
        consumer.max_retries = 1

        with patch("asyncio.sleep", AsyncMock()):
            await consumer.wrap_handle_message(mock_msg)
            await asyncio.sleep(0)

            # Wait for retries to complete
            await asyncio.gather(*consumer._retry_tasks.values(), return_exceptions=True)

            assert mock_msg.metadata.stream_seq not in consumer._message_attempts
            assert mock_msg.metadata.stream_seq not in consumer._retry_tasks
            assert consumer.total_error_count == 1

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
        mock_msg_1 = AsyncMock()
        mock_msg_1.metadata.stream_seq = 1
        mock_msg_1.data = {"id": 1}

        mock_msg_2 = AsyncMock()
        mock_msg_2.metadata.stream_seq = 2
        mock_msg_2.data = {"id": 2}

        mock_msg_3 = AsyncMock()
        mock_msg_3.metadata.stream_seq = 3
        mock_msg_3.data = {"id": 3}

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

        # Assert the order of execution
        assert consumer.events == [2, 3, 1, 1, 1, 1]

    @pytest.mark.asyncio
    async def test_handle_error_callback(self, consumer, mock_msg):
        # Mock the setup_subscriptions to avoid real NATS interaction
        consumer.setup_subscriptions = AsyncMock()
        # Mock the message handling
        mock_msg.metadata.stream_seq = 1
        mock_msg.data = {"id": 1}
        mock_msg.ack = AsyncMock()
        mock_msg.nak = AsyncMock()
        # Track if handle_error was called
        consumer.handle_error = AsyncMock()
        # Force max retries to be exceeded
        consumer.max_retries = 1
        with patch("asyncio.sleep", AsyncMock()):
            await consumer.wrap_handle_message(mock_msg)
        # Assert that handle_error was called
        consumer.handle_error.assert_called_once_with(mock_msg, ANY, 2)
        # Ensure correct default ack/nak behavior
        mock_msg.ack.assert_not_called()
        mock_msg.nak.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_error_ack_behavior_nak(self, consumer, mock_msg):
        # Set behavior to Nak
        consumer.setup_subscriptions = AsyncMock()
        consumer.handle_error = AsyncMock()

        mock_msg.ack = AsyncMock()
        mock_msg.nak = AsyncMock()

        consumer.max_retries = 1

        with patch("asyncio.sleep", AsyncMock()):
            await consumer.wrap_handle_message(mock_msg)

        consumer.handle_error.assert_called_once_with(mock_msg, ANY, 2)
        mock_msg.ack.assert_not_called()
        mock_msg.nak.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_error_ack_behavior_ack(self, consumer, mock_msg):
        # Set behavior to Ack
        consumer.handle_error_ack_behavior = ErrorAckBehavior.ACK
        consumer.setup_subscriptions = AsyncMock()
        consumer.handle_error = AsyncMock()

        mock_msg.ack = AsyncMock()
        mock_msg.nak = AsyncMock()

        consumer.max_retries = 1

        with patch("asyncio.sleep", AsyncMock()):
            await consumer.wrap_handle_message(mock_msg)

        consumer.handle_error.assert_called_once_with(mock_msg, ANY, 2)
        mock_msg.ack.assert_called_once()
        mock_msg.nak.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_error_ack_behavior_implemented_by_handle_error(self, consumer, mock_msg):
        # Set behavior to ImplementedByHandleError
        consumer.handle_error_ack_behavior = ErrorAckBehavior.IMPLEMENTED_BY_HANDLE_ERROR
        consumer.setup_subscriptions = AsyncMock()
        consumer.handle_error = AsyncMock()

        mock_msg.ack = AsyncMock()
        mock_msg.nak = AsyncMock()

        consumer.max_retries = 1

        with patch("asyncio.sleep", AsyncMock()):
            await consumer.wrap_handle_message(mock_msg)

        consumer.handle_error.assert_called_once_with(mock_msg, ANY, 2)
        mock_msg.ack.assert_not_called()
        mock_msg.nak.assert_not_called()


class TestDurableName:
    def test_get_durable_name_fallback(self, consumer):
        # Test fallback to default durable name
        assert consumer.get_durable_name() == "default"
        assert consumer.deliver_subject == "default.deliver"

        # Test using a custom durable name
        consumer.durable_name = "custom_durable"
        assert consumer.get_durable_name() == "custom_durable"
        assert consumer.deliver_subject == "custom_durable.deliver"
