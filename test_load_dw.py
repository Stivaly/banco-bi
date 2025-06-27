"""
    ETL Test script to bootstrap the Data Warehouse (DW) with initial data.
    Move this archive to the root of the ETL project to run it.
"""

from etl.transform.dim_builder import build_dim_cliente_df
from etl.load.dim_loaders import upsert_dim_cliente

from etl.transform.fact_builder import build_fact_cuenta_df
from etl.load.load_to_dw import insert_fact_cuenta

from etl.utils.logger import get_logger

logger = get_logger(__name__)

if __name__ == "__main__":
    try:
        logger.info("Bootstrap DW – dimensión cliente")
        dim_df = build_dim_cliente_df()
        upsert_dim_cliente(dim_df)
        logger.info("Dimensión cliente cargada.")

        logger.info("Bootstrap DW – fact_cuenta")
        fact_df = build_fact_cuenta_df()
        if fact_df.is_empty():
            logger.warning("fact_cuenta vacío – nada que cargar.")
        else:
            insert_fact_cuenta(fact_df)
            logger.info("Hechos cargados en DW.")

    except Exception as e:
        logger.exception("Falló la carga inicial del DW: %s", e)
