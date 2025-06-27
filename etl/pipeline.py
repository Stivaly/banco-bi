from etl.extract.excel_reader import read_excel_data
from etl.load.load_to_staging import load_dataframe_to_staging
from etl.extract.db_reader import read_staging_table
from etl.transform.data_cleaner import clean_clients, clean_accounts
from etl.load.load_to_db import upsert_clients, upsert_accounts, NoNewDataError

from etl.transform.dim_builder import build_dim_cliente_df          
from etl.load.dim_loaders import upsert_dim_cliente     
from etl.transform.fact_builder import build_fact_cuenta_df
from etl.load.load_to_dw import insert_fact_cuenta

from etl.load.cleanup import truncate_staging_table
from etl.utils.logger import get_logger

logger = get_logger(__name__)
STAGING_TABLE = "staging.DatosCasoEstudio"

def run_etl_pipeline() -> None:
    logger.info("=== ETL pipeline started ===")

    try:
        # 1. Excel ➜ Staging
        df_excel = read_excel_data()
        load_dataframe_to_staging(df_excel, table_name=STAGING_TABLE)

        # 2. Staging ➜ Transform ➜ Transaccional
        raw_df       = read_staging_table(STAGING_TABLE)
        clients_df   = clean_clients(raw_df)
        accounts_df  = clean_accounts(raw_df)

        logger.info("Data cleaning completed successfully.")
        logger.info("Loading cleaned data into the transactional database...")

        # try:
        upsert_clients(clients_df)
        #except NoNewDataError as exc:
        #    logger.info("Carga omitida: %s", exc)
        #    return
        upsert_accounts(accounts_df)

        logger.info("Data loaded into the transactional database successfully.")

        logger.info("Bootstrap DW - dimensión cliente")
        dim_df = build_dim_cliente_df()
        try:
            upsert_dim_cliente(dim_df)
        except NoNewDataError as e:
            logger.warning(str(e))
        logger.info("Dimensión cliente cargada.")

        logger.info("Bootstrap DW - fact_cuenta")
        fact_df = build_fact_cuenta_df()
        if fact_df.is_empty():
            logger.warning("fact_cuenta vacío - nada que cargar.")
        else:
            insert_fact_cuenta(fact_df)
            logger.info("Hechos cargados en DW.")            

        logger.info("=== ETL pipeline finished OK ===")

    except Exception as e:
        logger.error(f"ETL pipeline failed: {e}")
    finally:
        try:
            truncate_staging_table(STAGING_TABLE)
        except Exception as te:
            logger.error(f"Post-run TRUNCATE failed: {te}")
