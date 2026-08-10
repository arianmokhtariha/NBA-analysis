"""Database credentials, loaded from a local .env file.

Copy `.env.example` to `.env` and fill it in. `.env` is gitignored.
"""

import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


def get_env_variable(var_name: str, default: Optional[str] = None) -> str:
    """Get an environment variable, or raise if missing and no default."""
    value = os.getenv(var_name, default)
    if value is None:
        raise EnvironmentError(f"Missing required environment variable: {var_name}")
    return value


try:
    # Target database.
    DB_CONFIG: dict[str, str] = {
        "user": get_env_variable("DB_USER"),
        "password": get_env_variable("DB_PASSWORD"),
        "host": get_env_variable("DB_HOST"),
        "port": get_env_variable("DB_PORT"),
        "dbname": get_env_variable("DB_NAME"),
    }

    # Initial connection, used to create/drop the target database itself.
    DB_CONFIG_INIT: dict[str, str] = {
        "user": get_env_variable("DB_USER"),
        "password": get_env_variable("DB_PASSWORD"),
        "host": get_env_variable("DB_HOST"),
        "port": get_env_variable("DB_PORT"),
        "dbname": "postgres",
    }
except EnvironmentError as exc:
    print(f"Configuration Error: {exc}")
    raise
