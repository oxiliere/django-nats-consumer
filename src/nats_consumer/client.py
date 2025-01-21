import logging

from nats.aio.client import Client as NATS

from nats_consumer import settings

logger = logging.getLogger(__name__)


async def get_nats_client(**connection_args):
    nats_client = NATS()
    connect_args = connection_args if connection_args else settings.connect_args
    servers = connect_args.get("servers", [])
    try:
        logger.debug(f"Attempting to connect to NATS servers: {servers}")
        await nats_client.connect(**connect_args)
        logger.debug("Connected to NATS")
    except Exception as e:
        logger.error(f"Error connecting to NATS: {e}")
        raise
    return nats_client
