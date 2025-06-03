import pyodbc
import polars as pl
from etl.config import get_db_connection_string, ConfigError
from etl.utils.logger import get_logger

logger = get_logger(__name__)

def load_dataframe_to_staging(
    df: pl.DataFrame,
    table_name: str
) -> None:
    """
    Loads a Polars DataFrame into the staging table in SQL Server.

    Args:
        df (pl.DataFrame): DataFrame to load.
        table_name (str): Name of the staging table in the database.

    Raises:
        Exception: If loading fails.
    """
    if df.is_empty():
        logger.warning("Attempted to load an empty DataFrame. No data loaded.")
        return
    
    df = df.rename({col: col.strip() for col in df.columns})

    conn = None
    cursor = None
    try:
        conn = pyodbc.connect(get_db_connection_string(), autocommit=True)
        cursor = conn.cursor()
        logger.info(f"Connected to the database. Starting load into '{table_name}'.")

        columns = df.columns
        n_cols = len(columns)
        placeholders = ", ".join(["?"] * n_cols)
        columns_sql = ", ".join([f"[{col}]" for col in columns])

        insert_sql = f"INSERT INTO {table_name} ({columns_sql}) VALUES ({placeholders})"
        logger.info(f"Prepared insert statement for {n_cols} columns.")

        batch_size = 500
        rows = df.rows()
        total = len(rows)
        for i in range(0, total, batch_size):
            batch = rows[i:i+batch_size]
            cursor.executemany(insert_sql, batch)
            logger.info(f"Inserted rows {i+1} to {min(i+batch_size, total)} into '{table_name}'.")

        logger.info(f"Finished loading {total} rows into '{table_name}'.")
    except Exception as e:
        logger.error(f"Failed to load data into staging table '{table_name}': {e}")
        raise
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()
        logger.info("Database connection closed after loading.")
