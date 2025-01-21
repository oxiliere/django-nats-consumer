import importlib
import logging

from django.apps import AppConfig
from django.conf import settings

logger = logging.getLogger(__name__)


class NatsConsumerConfig(AppConfig):
    name = "nats_consumer"
    label = "nats_consumer"
    verbose_name = "Django NATS Consumer"

    def ready(self):
        # Iterate over all installed apps
        for app in settings.INSTALLED_APPS:
            if app != "nats_consumer":
                # Try to import the consumers module for each app
                try:
                    importlib.import_module(f"{app}.consumers")
                except ModuleNotFoundError:
                    pass
                except Exception:
                    pass

        # Also try to load the topmost consumers module
        try:
            importlib.import_module("consumers")
        except ModuleNotFoundError:
            pass
        except Exception:
            pass
