from unittest.mock import AsyncMock, Mock, patch

import pytest
from nats.js.api import StreamConfig, StreamInfo
from nats.js.errors import NotFoundError

from nats_consumer.operations import CreateOrUpdateStream, CreateStream, DeleteStream, UpdateStream


@pytest.fixture
def mock_jetstream_instance():
    instance = Mock(
        stream_info=AsyncMock(),
        add_stream=AsyncMock(),
        update_stream=AsyncMock(),
        delete_stream=AsyncMock(),
    )
    return instance


@pytest.fixture
def mock_jetstream(mock_jetstream_instance):
    jetstream_mock = Mock()
    jetstream_mock.return_value = mock_jetstream_instance
    return jetstream_mock


@pytest.fixture
def mock_nats_client(mock_jetstream):
    # Create an AsyncMock for the NATS client
    client = AsyncMock(
        jetstream=mock_jetstream,
        drain=AsyncMock(),
        close=AsyncMock(),
    )
    return client


@pytest.mark.asyncio
async def test_create_stream(
    mock_nats_client,
    mock_jetstream_instance,
):
    stream_name = "test_stream"
    retention = "workqueue"
    subjects = ["test.>"]

    create_op = CreateStream(name=stream_name, retention=retention, subjects=subjects)

    mock_jetstream_instance.stream_info.side_effect = NotFoundError()
    with patch("nats_consumer.operations.get_nats_client", return_value=mock_nats_client):
        await create_op.execute()

    mock_jetstream_instance.add_stream.assert_awaited_once()

    config = mock_jetstream_instance.add_stream.call_args[0][0]
    assert config.name == stream_name
    assert config.retention == retention
    assert config.subjects == subjects

    # Assert the NATS client was drained and closed since it was created
    mock_nats_client.drain.assert_awaited_once()
    mock_nats_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_stream_exists(mock_nats_client, mock_jetstream_instance):
    stream_name = "test_stream"
    retention = "workqueue"
    subjects = ["test.>"]

    create_op = CreateStream(name=stream_name, retention=retention, subjects=subjects)
    with patch("nats_consumer.operations.get_nats_client", return_value=mock_nats_client):
        await create_op.execute()

    mock_nats_client.jetstream.assert_called_once()

    actual_stream_name = mock_jetstream_instance.stream_info.call_args[0][0]
    assert actual_stream_name == stream_name

    # Assert the NATS client was drained and closed since it was created
    mock_nats_client.drain.assert_awaited_once()
    mock_nats_client.close.assert_awaited_once()


async def test_delete_stream(mock_nats_client, mock_jetstream_instance):
    stream_name = "test_stream"
    delete_op = DeleteStream(stream_name)

    mock_jetstream_instance.stream_info.return_value = StreamInfo(stream_name, StreamConfig(name=stream_name))

    with patch("nats_consumer.operations.get_nats_client", return_value=mock_nats_client):
        await delete_op.execute()

    mock_jetstream_instance.delete_stream.assert_awaited_once_with(stream_name)
    mock_nats_client.drain.assert_awaited_once()
    mock_nats_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_stream(mock_nats_client, mock_jetstream_instance):
    # Arrange
    stream_name = "test_stream"
    new_subjects = ["updated.>"]

    update_op = UpdateStream(name=stream_name, subjects=new_subjects)

    with patch("nats_consumer.operations.get_nats_client", return_value=mock_nats_client):
        await update_op.execute()

    mock_jetstream_instance.stream_info.assert_called_once_with(stream_name)
    mock_jetstream_instance.update_stream.assert_awaited_once()

    config = mock_jetstream_instance.update_stream.call_args[0][0]
    assert config.name == stream_name
    assert config.subjects == new_subjects

    mock_nats_client.drain.assert_awaited_once()
    mock_nats_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_stream_not_found(mock_nats_client, mock_jetstream_instance):
    # Arrange
    stream_name = "test_stream"
    new_subjects = ["updated.>"]

    update_op = UpdateStream(name=stream_name, subjects=new_subjects)

    mock_jetstream_instance.stream_info.side_effect = NotFoundError()

    with patch("nats_consumer.operations.get_nats_client", return_value=mock_nats_client):
        await update_op.execute()

    mock_jetstream_instance.update_stream.assert_not_called()

    mock_nats_client.drain.assert_awaited_once()
    mock_nats_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_or_update_stream(mock_nats_client, mock_jetstream_instance):
    stream_name = "test_stream"
    retention = "workqueue"
    subjects = ["test.>"]

    create_or_update_op = CreateOrUpdateStream(name=stream_name, retention=retention, subjects=subjects)

    mock_jetstream_instance.stream_info.side_effect = NotFoundError()
    with patch("nats_consumer.operations.get_nats_client", return_value=mock_nats_client):
        await create_or_update_op.execute()

    mock_jetstream_instance.add_stream.assert_awaited_once()
    mock_nats_client.drain.assert_awaited_once()
    mock_nats_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_or_update_stream_exists(mock_nats_client, mock_jetstream_instance):
    stream_name = "test_stream"
    retention = "workqueue"
    subjects = ["test.>"]

    create_or_update_op = CreateOrUpdateStream(name=stream_name, retention=retention, subjects=subjects)

    mock_jetstream_instance.stream_info.return_value = StreamInfo(
        stream_name, StreamConfig(name=stream_name, retention=retention, subjects=subjects)
    )
    with patch("nats_consumer.operations.get_nats_client", return_value=mock_nats_client):
        await create_or_update_op.execute()

    mock_jetstream_instance.update_stream.assert_awaited_once()
    mock_nats_client.drain.assert_awaited_once()
    mock_nats_client.close.assert_awaited_once()
