import polars as pl
from etl.config import get_excel_file_path, get_db_connection_string, ConfigError
from etl.utils.logger import get_logger

logger = get_logger(__name__)
REQUIRED_COLUMNS = [
    "FECHA DE NACIMIENTO",
    "RUT",
    "NIVEL EDUCACIONAL DECLARADO",
    "SEXO",
    "ESTADO CIVIL",
    "ACTIVIDAD",
    "INGRESO MENSUAL PROMEDIO",
    "TOTAL DE CONTACTOS",
    "PUNTUACIÓN PROMEDIO",
    "REGIÓN",
    "FECHA APERTURA CUENTA",
    "USO DE TARJETA MENSUALMENTE",
    "SALDO MAXIMO REGISTRADO",
    "NUMERO DE CUENTA",
    "TIPO CUENTA",
    "VECES SALDO CERO",
]

def read_excel_data() -> pl.DataFrame:
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

        df = pl.read_excel(file_path) 
        logger.info(f"Successfully read Excel file: {file_path}")

        missing_columns = [col for col in REQUIRED_COLUMNS if col not in df.columns]
        if missing_columns:
            error_msg = f"Missing required columns: {missing_columns}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        for col in REQUIRED_COLUMNS:
            if df[col].null_count() > 0:
                # Filtrar filas donde el campo está nulo
                invalid_rows = df.filter(df[col].is_null())

                # Extraer los ruts de esas filas
                ruts_with_null = invalid_rows.get_column("RUT").to_list()

                error_msg = (
                    f"Column '{col}' contains missing (null) values. "
                    f"RUTs with missing data in this column: {ruts_with_null}"
                )
                logger.error(error_msg)
                raise ValueError(error_msg)
            
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

