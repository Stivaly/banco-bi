import pyodbc
import polars as pl
from etl.config import get_staging_connection_string
from etl.utils.logger import get_logger

logger = get_logger(__name__)

def read_staging_table(table_name: str) -> pl.DataFrame:
    """
    Reads all data from a staging table into a Polars DataFrame.

    Args:
        table_name (str): Name of the staging table (e.g. 'staging.DatosCasoEstudio').

    Returns:
        pl.DataFrame: DataFrame containing the raw staging data.

    Raises:
        Exception: If the read operation fails.
    """
    conn = None
    try:
        logger.info(f"Connecting to staging DB to read '{table_name}'.")
        conn = pyodbc.connect(get_staging_connection_string())
        query = f"SELECT * FROM {table_name}"
        logger.debug(f"Running query: {query}")
        df = pl.read_database(query, connection=conn)
        logger.info(f"Read {df.height} rows from '{table_name}'.")

        return df

    except Exception as e:
        logger.error(f"Failed to read table '{table_name}' from staging DB: {e}")
        raise

    finally:
        if conn is not None:
            conn.close()
            logger.info("Staging DB connection closed after read operation.")
