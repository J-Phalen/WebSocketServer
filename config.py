import logging
from pathlib import Path

from dotenv import dotenv_values

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")


def get_config() -> dict:
    """Returns the configuration as a dict object"""
    conf_file = Path(__file__).resolve().parent / "config.env"
    if not conf_file.exists():
        print("Configuration file not found...")
        raise SystemExit
    return dotenv_values(conf_file)


# Creates the Configuration dict variable, and updates it with any list values needed.
Configuration = get_config()
