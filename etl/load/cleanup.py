# etl/load/cleanup.py
import pyodbc
from etl.config import get_staging_connection_string
from etl.utils.logger import get_logger

logger = get_logger(__name__)

def truncate_staging_table(table_name: str) -> None:
    """
    Executes a TRUNCATE TABLE on the given staging table.

    Args:
        table_name (str): Fully-qualified table name (e.g. 'staging.DatosCasoEstudio').
    """
    conn = None
    try:
        logger.info(f"Truncating staging table '{table_name}' …")
        conn = pyodbc.connect(get_staging_connection_string(), autocommit=True)
        conn.cursor().execute(f"TRUNCATE TABLE {table_name}")
        logger.info(f"Staging table '{table_name}' truncated successfully.")
    except Exception as e:
        logger.error(f"Failed to truncate staging table '{table_name}': {e}")
        raise
    finally:
        if conn:
            conn.close()
            logger.debug("Staging DB connection closed after TRUNCATE.")
