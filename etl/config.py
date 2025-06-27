import os
from dotenv import load_dotenv
from functools import lru_cache
from etl.utils.logger import get_logger 

logger = get_logger(__name__)

class ConfigError(Exception):
    """Custom exception for configuration errors."""
    pass

load_dotenv()
logger.info("Loaded environment variables from .env file.")

def get_excel_file_path(data_folder: str = "data") -> str:
    valid_extensions = ('.xls', '.xlsx')
    files = [
        f for f in os.listdir(data_folder)
        if f.lower().endswith(valid_extensions)
    ]

    if len(files) == 0:
        logger.error(f"No Excel file found in '{data_folder}'.")
        raise ConfigError(f"No se encontró ningún archivo Excel en la carpeta '{data_folder}'.")
    if len(files) > 1:
        logger.error(f"Multiple Excel files found in '{data_folder}': {files}")
        raise ConfigError(f"""Se encontraron múltiples archivos Excel en la carpeta '{data_folder}': {files}. 
                          Por favor, asegúrate de que solo haya un archivo Excel en esa carpeta.""")

    excel_path = os.path.abspath(os.path.join(data_folder, files[0]))
    logger.info(f"Excel file path resolved: {excel_path}")
    return excel_path

def get_staging_connection_string() -> str:
    """
    Builds and returns the data staging connection string using environment variables.

    Returns:
        str: Data staging connection string.

    Raises:
        ConfigError: If any required environment variable is missing.
    """
    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT")
    db_name = os.getenv("DB_STAGING")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")

    if not all([db_host, db_port, db_name, db_user, db_password]):
        logger.error("Missing required environment variables for data staging connection.")
        raise ConfigError("Missing one or more required environment variables for the data staging connection.")

    connection_string = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={db_host},{db_port};"
        f"DATABASE={db_name};"
        f"UID={db_user};"
        f"PWD={db_password};"
        "TrustServerCertificate=yes;"
    )

    logger.info("Data staging connection string constructed successfully.")
    return connection_string

@lru_cache
def get_db_connection_string() -> str:
    """
    Builds and returns the database connection string using environment variables.

    Returns:
        str: Database connection string.

    Raises:
        ConfigError: If any required environment variable is missing.
    """
    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT")
    db_name = os.getenv("DB_TRANSACT")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")

    if not all([db_host, db_port, db_name, db_user, db_password]):
        logger.error("Missing required environment variables for database connection.")
        raise ConfigError("Missing one or more required environment variables for the database connection.")

    connection_string = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={db_host},{db_port};"
        f"DATABASE={db_name};"
        f"UID={db_user};"
        f"PWD={db_password};"
        "TrustServerCertificate=yes;"
    )

    # logger.info("Database connection string constructed successfully.")
    return connection_string

@lru_cache
def get_dwh_connection_string() -> str:
    """
    Builds and returns the datawarehouse connection string using environment variables.

    Returns:
        str: Datawarehouse connection string.

    Raises:
        ConfigError: If any required environment variable is missing.
    """
    dw_host = os.getenv("DW_HOST")
    dw_port = os.getenv("DW_PORT")
    dw_name = os.getenv("DW_NAME")
    dw_user = os.getenv("DW_USER")
    dw_password = os.getenv("DW_PASSWORD")

    if not all([dw_host, dw_port, dw_name, dw_user, dw_password]):
        logger.error("Missing required environment variables for datawarehouse connection.")
        raise ConfigError("Missing one or more required environment variables for the datawarehouse connection.")

    connection_string = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={dw_host},{dw_port};"
        f"DATABASE={dw_name};"
        f"UID={dw_user};"
        f"PWD={dw_password};"
        "TrustServerCertificate=yes;"
    )

    logger.info("Datawarehouse connection string constructed successfully.")
    return connection_string
