import polars as pl
import pyodbc
from etl.utils.logger import get_logger
from etl.config import get_dwh_connection_string
from etl.load.dim_loaders import (
    upsert_dim_cliente,
    upsert_dim_region,
    upsert_dim_time,
)

logger = get_logger(__name__)

class NoNewFactDataError(RuntimeError):
    """Raised when there are no new fact_cuenta rows to insert."""

def insert_fact_cuenta(df_fact_nat: pl.DataFrame) -> None:
    """Takes a fact DataFrame with natural keys and loads it with surrogate keys."""
    # --- 1. Build dimension mappings ---
    cliente_map  = upsert_dim_cliente(df_fact_nat)
    region_map   = upsert_dim_region(df_fact_nat)
    date_map     = upsert_dim_time(df_fact_nat)

    # --- 2. Replace natural → surrogate (vectorised) ---
    df_fact = (
        df_fact_nat
        .with_columns(
            pl.col("rut_cliente").map_elements(cliente_map.get, return_dtype=pl.Int64).alias("cliente_key"),

            pl.col("id_region").map_elements(region_map.get, return_dtype=pl.Int64).alias("region_key"),

            pl.col("fecha").cast(str).map_elements(date_map.get, return_dtype=pl.Int64).alias("date_key")
        )
        .drop(["rut_cliente", "id_region", "fecha"])
        .select([
            "cliente_key", "region_key", "date_key",
            "tipo_cuenta", "saldo_maximo", "veces_saldo_cero",
            "uso_tarjeta_mensual", "movimientos_mensuales",
            "probabilidad_fuga",
        ])
    )

    # Query existing ones
    with pyodbc.connect(get_dwh_connection_string()) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT cliente_key, region_key, date_key, tipo_cuenta
            FROM dbo.fact_cuenta
        """)
        existing = set(tuple(row) for row in cur.fetchall())
        cur.close()
    logger.debug("Existing composite keys loaded: %d", len(existing))

    # Filter only new rows
    def row_key(row): 
        return (row["cliente_key"], row["region_key"], row["date_key"], row["tipo_cuenta"])

    df_fact = df_fact.with_columns(
        pl.struct(["cliente_key", "region_key", "date_key", "tipo_cuenta"])
        .map_elements(lambda row: row_key(row) in existing, return_dtype=pl.Boolean)
        .alias("is_existing")
    )

    df_to_insert = df_fact.filter(~pl.col("is_existing")).drop("is_existing")

    # If no new rows, abort early
    if df_to_insert.is_empty():
        raise NoNewFactDataError("No new fact_cuenta rows to insert - process aborted.")

    # --- 3. Bulk-insert into fact_cuenta -----------------
    insert_cols = ", ".join(df_to_insert.columns)
    placeholders = ", ".join(["?"] * len(df_to_insert.columns))
    sql = f"INSERT INTO dbo.fact_cuenta ({insert_cols}) VALUES ({placeholders})"

    with pyodbc.connect(get_dwh_connection_string()) as conn:
        cur = conn.cursor()
        cur.fast_executemany = True
        cur.executemany(sql, df_to_insert.rows())
        conn.commit()
        cur.close()
    logger.info("Loaded %d fact rows", df_to_insert.height)