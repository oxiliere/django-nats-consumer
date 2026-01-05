from unittest.mock import AsyncMock, patch

import pytest

from nats_consumer.client import get_nats_client
from nats_consumer import settings as nats_settings


@pytest.mark.asyncio
async def test_get_nats_client_with_django_settings():
    with patch("nats_consumer.client.NATS") as mock_nats_class:
        mock_client = AsyncMock()
        mock_nats_class.return_value = mock_client
        
        client = await get_nats_client()
        
        # Verify connect was called with nats_consumer settings
        mock_client.connect.assert_called_once_with(**nats_settings.connect_args)
        assert client is mock_client


@pytest.mark.asyncio
async def test_get_nats_client_with_args():
    with patch("nats_consumer.client.NATS") as mock_nats_class:
        mock_client = AsyncMock()
        mock_nats_class.return_value = mock_client
        
        connect_args = {"servers": ["nats://localhost:4222"]}
        client = await get_nats_client(**connect_args)
        
        # Verify connect was called with provided args
        mock_client.connect.assert_called_once_with(**connect_args)
        assert client is mock_client
