import importlib
import inspect
import json
import logging
import os
from typing import Text
import pkg_resources
import yaml
from schema import Schema, And, Use, Optional, Or, SchemaError

from mgw_svc_core.transformers_core.WebrtcServicePluginInterface import (
    WebRTCServicePluginInterface,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Define the schema for iceServer
iceserver_schema = Schema({"url": [str], "username": str, "credential": str})

# Define the schema for the server
server_schema = Schema({"iceserver": iceserver_schema}, ignore_extra_keys=True)

# Define the schema for the transformers
transformer_schema = Schema({"name": str, "options": {str: object}})

# Define the overall schema
config_schema = Schema(
    {Optional("server"): server_schema, Optional("transformers"): [transformer_schema]},
    ignore_extra_keys=True,
)


# schema_path = pkg_resources.resource_filename(__name__, "schemas/config.yaml")
schema_path = pkg_resources.resource_filename(__name__, "schemas/config.json")

with open(schema_path, "r") as file:
    schema_data = yaml.safe_load(file)


def load_config(file_path: str):
    with open(file_path, "r") as file:
        return yaml.safe_load(file)


def validate_config(configuration):
    try:
        # config_schema = Schema(schema_data)
        config_schema.validate(configuration)
        print("Configuration format is valid.")
    except SchemaError as se:
        print(f"Schema error: {se}")


def class_from_module(module_path: Text):
    _class = None
    if "." in module_path:
        module_name, _, class_name = module_path.rpartition(".")
        m = importlib.import_module(module_name)
        _class = getattr(m, class_name)
    else:
        m = importlib.import_module(module_path)
        _class = m.plugin_class

    if _class is None:
        raise ImportError(f"Cannot retrieve class from path {module_path}.")

    if not inspect.isclass(_class):
        raise ModuleNotFoundError(
            f"`class_from_module_path()` is expected to return a class, "
            f"but for {module_path} we got a {type(_class)}."
        )
    return _class


def get_class_directory(cls):
    return os.path.dirname(os.path.realpath(inspect.getfile(cls)))

def load_and_register_transformers_plugin(transformers):

    logger.debug(f"load_and_register_transformers_plugin {transformers}")

    for transformer in transformers:
        plugin = class_from_module(transformer.get("name"))
        logger.info(f"Loading and registering plugin: {plugin}")

        # Check if any parent class has the same name as WebRTCServicePluginInterface
        if not any(base.__name__ == WebRTCServicePluginInterface.__name__ for base in plugin.__bases__):
            logger.error(f"Failed to register plugin {plugin}: no plugin base name is WebRTCServicePluginInterface")
            logger.debug(f"load_and_register_transformers_plugin WebRTCServicePluginInterface name: {WebRTCServicePluginInterface.__name__}")
            logger.debug(f"load_and_register_transformers_plugin bases: {plugin.__bases__}")
            for base in plugin.__bases__:
                logger.debug(f"load_and_register_transformers_plugin name of base {base} is {base.__name__}")
            continue

        # Check if any parent class is in the same directory as WebRTCServicePluginInterface
        webrtc_dir = get_class_directory(WebRTCServicePluginInterface)
        if any(get_class_directory(base) == webrtc_dir for base in plugin.__bases__):
            # continue
            logger.info(f"load_and_register_transformers_plugin calling register for {plugin}")
            plugin().Register(transformer.get('options', {}))
        else:
            logger.error(f"Failed to register plugin {plugin}: no plugin base is webrtc_dir")
            logger.debug(f"load_and_register_transformers_plugin webrtc_dir: {webrtc_dir}")
            logger.debug(f"load_and_register_transformers_plugin bases: {plugin.__bases__}")
            for base in plugin.__bases__:
                logger.debug(f"load_and_register_transformers_plugin class directory of base {base} is {get_class_directory(base)}")
