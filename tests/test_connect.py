from unittest.mock import AsyncMock, patch

import pytest

from example.nats_example import settings
from nats_consumer.client import get_nats_client


@patch("nats_consumer.client.NATS.connect", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_get_nats_client_with_django_settings(mock_connect):
    client = await get_nats_client()
    mock_connect.assert_called_with(**settings.NATS_CONSUMER["connect_args"])
    assert client is not None


@patch("nats_consumer.client.NATS.connect", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_get_nats_client_with_args(mock_connect):
    connect_args = {"servers": ["nats://localhost:4222"]}
    client = await get_nats_client(**connect_args)
    mock_connect.assert_called_with(**connect_args)
    assert client is not None
