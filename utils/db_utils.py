from typing import Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from db_config import DB_CONFIG

# create engine once at module level
_engine = None


def get_engine():
    """Returns a singleton SQLAlchemy engine connected to PostgreSQL."""
    global _engine
    if _engine is None:
        try:
            cfg = DB_CONFIG
            url = (
                f"postgresql+psycopg2://{cfg['user']}:{cfg['password']}"
                f"@{cfg['host']}:{cfg['port']}/{cfg['dbname']}"
            )
            _engine = create_engine(url)
        except Exception as e:
            raise RuntimeError(f"Database connection failed: {e}")
    return _engine


def run_query(query: str, params: Optional[dict] = None) -> Optional[pd.DataFrame]:
    """
    Executes a SELECT query and returns results as a DataFrame.

    Args:
        query: SQL SELECT statement
        params: Optional parameters for parameterized queries

    Returns:
        DataFrame with query results, or None if query fails
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            return pd.read_sql_query(text(query), conn, params=params)
    except SQLAlchemyError as e:
        print(f"✗ Query failed: {e}")
        return None


def execute_ddl(query: str, params: Optional[dict] = None) -> bool:
    """
    Executes DDL/DML statements (ALTER, CREATE, UPDATE, DELETE, etc.).
    Auto-commits on success, rolls back on error.

    Args:
        query: SQL DDL/DML statement to execute
        params: Optional parameters for parameterized queries

    Returns:
        bool: True if successful

    Raises:
        RuntimeError: If database connection fails
        SQLAlchemyError: If SQL execution fails
    """

    engine = get_engine()
    if engine is None:
        raise RuntimeError("Database connection unavailable")

    try:
        with engine.begin() as conn:  # Auto-commits on success, rolls back on error
            result = conn.execute(text(query), params or {})
            print(f"✓ Query executed successfully. Rows affected: {result.rowcount}")
            return True

    except SQLAlchemyError as e:
        print(f"✗ Query failed: {e}")
        raise  # Re-raise so caller knows it failed
