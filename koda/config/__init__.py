"""Configuration module for koda."""

from koda.config.loader import load_config, get_config_path
from koda.config.schema import Config

__all__ = ["Config", "load_config", "get_config_path"]
