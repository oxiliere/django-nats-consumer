from typing import Any, Dict

from django.conf import settings

CONFIG_DEFAULTS = {
    "allow_reconnect": True,
    "max_reconnect_attempts": 5,
    "reconnect_time_wait": 1,
    "connect_timeout": None,
}


def get_config(settings_name=None):
    if settings_name is None:
        settings_name = "NATS_CONSUMER"

    def merge_dicts(dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
        result = dict1.copy()

        for key, value in dict2.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = merge_dicts(result[key], value)
            else:
                result[key] = value

        return result

    return merge_dicts(CONFIG_DEFAULTS, getattr(settings, settings_name, {}))


config = get_config()

nats_servers = config.get("nats_servers")
if not isinstance(nats_servers, list):
    raise ValueError("nats_servers must be a list")

allow_reconnect = config.get("allow_reconnect", True)
max_reconnect_attempts = config.get("max_reconnect_attempts", 5)
reconnect_time_wait = config.get("reconnect_time_wait", 1)
connect_timeout = config.get("connect_timeout", None)

connection_args = {}
if allow_reconnect:
    connection_args["allow_reconnect"] = allow_reconnect
if max_reconnect_attempts:
    connection_args["max_reconnect_attempts"] = max_reconnect_attempts
if reconnect_time_wait:
    connection_args["reconnect_time_wait"] = reconnect_time_wait
if connect_timeout:
    connection_args["connect_timeout"] = connect_timeout
