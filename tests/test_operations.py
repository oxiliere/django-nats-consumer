import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from nats.js.api import StreamConfig

from nats_consumer.operations import CreateStream, DeleteStream, UpdateStream, GetStream


@pytest.fixture
def mock_js():
    return AsyncMock()


@pytest.fixture
def mock_nats_client():
    client = AsyncMock()
    client.js = mock_js()
    return client


@pytest.mark.asyncio
async def test_create_stream():
    # Arrange
    stream_name = "test_stream"
    retention = "workqueue"
    subjects = ["test.>"]

    create_op = CreateStream(name=stream_name, retention=retention, subjects=subjects)

    mock_client = AsyncMock()
    mock_js = AsyncMock()
    mock_client.js.return_value = mock_js

    # Act
    with patch("nats_consumer.operations.get_nats_client", return_value=mock_client):
        await create_op.execute()

    # Assert
    mock_client.js.assert_called_once()
    mock_js.add_stream.assert_called_once()

    # Verify the StreamConfig passed to add_stream
    called_config = mock_js.add_stream.call_args[0][0]
    assert isinstance(called_config, StreamConfig)
    assert called_config.name == stream_name
    assert called_config.retention == retention
    assert called_config.subjects == subjects


@pytest.mark.asyncio
async def test_delete_stream():
    # Arrange
    stream_name = "test_stream"
    delete_op = DeleteStream(stream_name)

    mock_client = AsyncMock()
    mock_js = AsyncMock()
    mock_client.js.return_value = mock_js

    # Act
    with patch("nats_consumer.operations.get_nats_client", return_value=mock_client):
        await delete_op.execute()

    # Assert
    mock_client.js.assert_called_once()
    mock_js.delete_stream.assert_called_once_with(stream_name)


@pytest.mark.asyncio
async def test_get_stream():
    # Arrange
    stream_name = "test_stream"
    get_op = GetStream(stream_name)

    mock_client = AsyncMock()
    mock_js = AsyncMock()
    mock_client.js.return_value = mock_js

    # Act
    with patch("nats_consumer.operations.get_nats_client", return_value=mock_client):
        await get_op.execute()

    # Assert
    mock_client.js.assert_called_once()
    mock_js.stream_info.assert_called_once_with(stream_name)


@pytest.mark.asyncio
async def test_update_stream():
    # Arrange
    stream_name = "test_stream"
    new_subjects = ["updated.>"]

    update_op = UpdateStream(name=stream_name, subjects=new_subjects)

    mock_client = AsyncMock()
    mock_js = AsyncMock()
    mock_client.js.return_value = mock_js

    # Act
    with patch("nats_consumer.operations.get_nats_client", return_value=mock_client):
        await update_op.execute()

    # Assert
    mock_client.js.assert_called_once()
    mock_js.update_stream.assert_called_once()

    # Verify the StreamConfig passed to update_stream
    called_config = mock_js.update_stream.call_args[0][0]
    assert isinstance(called_config, StreamConfig)
    assert called_config.name == stream_name
    assert called_config.subjects == new_subjects
