import polars as pl
from etl.config import get_excel_file_path, get_db_connection_string, ConfigError
from etl.utils.logger import get_logger


logger = get_logger(__name__)

def read_excel_data(sheet_name: str = None) -> pl.DataFrame:
    """
    Reads data from the Excel file located in the data folder.

    Args:
        sheet_name (str, optional): The name of the sheet to read. If None, reads the first sheet.

    Returns:
        pl.DataFrame: The data extracted from the Excel file.

    Raises:
        ConfigError: If there are issues with finding the Excel file.
        FileNotFoundError: If the Excel file cannot be found at the resolved path.
        ValueError: If the sheet name is not found.
    """
    try:
        file_path = get_excel_file_path()
        logger.info(f"Reading Excel file from {file_path}")

        if sheet_name:
            df = pl.read_excel(file_path, sheet_name=sheet_name)
        else:
            df = pl.read_excel(file_path) 

        logger.info(f"Successfully read Excel file: {file_path}")
        return df

    except ConfigError as e:
        logger.error(f"Configuration error: {e}")
        raise
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error while reading Excel file: {e}")
        raise

