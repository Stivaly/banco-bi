from etl.extract.excel_reader import read_excel_data
from etl.load.load_to_staging import load_dataframe_to_staging
from etl.utils.logger import get_logger

logger = get_logger(__name__)

def run_etl_pipeline():
    logger.info("Starting ETL pipeline...")

    try:
        # 1. EXTRACTION
        logger.info("Extracting data from Excel...")
        df = read_excel_data()

        # 2. LOAD
        logger.info("Loading data into staging table...")
        load_dataframe_to_staging(df, table_name="staging.DatosCasoEstudio")

        logger.info("ETL pipeline finished successfully.")
    except Exception as e:
        logger.error(f"ETL pipeline failed: {e}")
