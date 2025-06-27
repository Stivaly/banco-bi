# etl/load/load_to_db.py – client & account upserts with robust region handling
# --------------------------------------------------------------------------
# ▸ upsert_clients(df_clients): Inserts new customers ensuring region_id FK is correctly set.
# ▸ upsert_accounts(df_accounts): Inserts new bank accounts while preserving FK integrity.
#
# Both DataFrames arrive *transformed* — i.e. cleaned and typed — but still
# preserve the **original Excel headers**.  We keep those headers until the
# moment we rename the columns, so the mapping is concentrated in one place.
#
# IMPORTANT RULES (project‑wide):
#   • No business logic in the DAG files.
#   • No hard‑coded connection strings or paths.
#   • Variable names in English.
#   • No Polars .apply – we rely on vectorised ops / map_elements.
#
# This module complies with those rules and avoids the pyodbc 17 bug triggered
# by DECIMAL parameters + fast_executemany.

from typing import Dict, List, Set

import pyodbc
import polars as pl

from etl.transform.data_cleaner import normalize_string
from etl.transform.data_cleaner import is_valid_rut
from etl.config import get_db_connection_string
from etl.utils.logger import get_logger

logger = get_logger(__name__)


class NoNewDataError(RuntimeError):
    """Raised when there are no new rows to insert in the source file."""


###############################################################################
# Helper utilities                                                            #
###############################################################################

def _fetch_existing_values(conn: pyodbc.Connection) -> Set[str]:
    """Fetch all existing RUTs from the database into a set."""
    with conn.cursor() as cur:
        cur.execute("SELECT rut_cliente FROM dbo.Cliente")
        return {row[0] for row in cur.fetchall()}
    
def _fetch_existing_account_ids(conn: pyodbc.Connection) -> Set[int]:
    """Fetch all existing account IDs from the database into a set."""
    with conn.cursor() as cur:
        cur.execute("SELECT id_cuenta FROM dbo.Cuenta")
        return {row[0] for row in cur.fetchall()}

###############################################################################
# Region helpers (fallback only for clients)                                  #
###############################################################################

def _build_region_lookup(cur: pyodbc.Cursor) -> Dict[str, int]:
    """Return a dict: *normalized region name* → *id_region* (surrogate key)."""

    cur.execute("SELECT id_region, nombre_region FROM dbo.Region")
    lookup: Dict[str, int] = {}
    for id_region, region_name in cur.fetchall():
        raw = region_name.strip().lower()
        lookup[raw] = id_region
        lookup[normalize_string(raw)] = id_region  # remove punctuation / accents
    return lookup


def _ensure_region_column(df: pl.DataFrame) -> pl.DataFrame:
    """Ensure there is a **Region** column (fallback to 'REGIÓN' if needed)."""

    if "Region" in df.columns:
        return df
    if "REGIÓN" in df.columns:
        return df.with_columns(pl.col("REGIÓN").alias("Region"))
    return df


def _fallback_map_id_region(df: pl.DataFrame, lookup: Dict[str, int]) -> pl.DataFrame:
    """Vectorized region-to-id mapping using normalized join (faster than map_elements)."""

    df = _ensure_region_column(df)

    if "Region" not in df.columns:
        raise ValueError("Cannot map region: 'Region' column not present in DataFrame")

    # 1. Crear tabla de regiones desde el lookup dict
    region_df = pl.DataFrame({
        "Region_normalized": list(lookup.keys()),
        "id_region": list(lookup.values())
    })

    # 2. Agregar columna normalizada a df de entrada
    df = df.with_columns([
        pl.col("Region").map_elements(
            lambda r: normalize_string(r.strip().lower()) if r is not None else None,
            return_dtype=pl.Utf8
        ).alias("Region_normalized")
    ])

    # 3. Join vectorizado por Region_normalized
    df = df.join(region_df, on="Region_normalized", how="left").drop("Region_normalized")

    return df


def _export_problem_rows(df_missing: pl.DataFrame, label: str) -> None:
    """Log (to console) the rows whose region could **not** be mapped."""

    if df_missing.height == 0:
        return

    rut_col = "RUT" if "RUT" in df_missing.columns else "rut_cliente"
    region_col = (
        "Region"
        if "Region" in df_missing.columns
        else "REGIÓN"
        if "REGIÓN" in df_missing.columns
        else None
    )
    cols = [rut_col] + ([region_col] if region_col else [])

    details = df_missing.select(cols).to_string()
    logger.warning("[%s] %d rows skipped - region not found:\n%s", label, df_missing.height, details)


###############################################################################
# Upsert CLIENTS                                                              #
###############################################################################

def upsert_clients(df_clients: pl.DataFrame) -> None:
    conn_str = get_db_connection_string()
    with pyodbc.connect(conn_str, autocommit=False) as conn:
        try:
            cur = conn.cursor()

            df_work = df_clients.clone()
            if "id_region" not in df_work.columns:
                logger.info("'id_region' no presente; aplicando mapeo de respaldo desde Region.")
                lookup = _build_region_lookup(cur)
                df_work = _fallback_map_id_region(df_work, lookup)

            df_missing = df_work.filter(pl.col("id_region").is_null())
            _export_problem_rows(df_missing, "clients")
            df_valid = df_work.filter(pl.col("id_region").is_not_null())
            if df_valid.is_empty():
                logger.info("No valid client rows to insert after region check - aborting.")
                conn.rollback()
                return

            # Mapeo usando encabezados originales del Excel
            cols_map = {
                "RUT": "rut_cliente",
                "FECHA DE NACIMIENTO": "fecha_nacimiento",
                "NIVEL EDUCACIONAL DECLARADO": "nivel_educacional",
                "SEXO": "sexo",
                "ESTADO CIVIL": "estado_civil",
                "ACTIVIDAD": "actividad",
                "INGRESO MENSUAL PROMEDIO": "ingreso_mensual_promedio",
                "PUNTUACIÓN PROMEDIO": "puntuacion_promedio",
                "TOTAL DE CONTACTOS": "cantidad_contactos",
                "id_region": "region_id",
            }
            df_out = df_valid.select(list(cols_map.keys())).rename(cols_map)
            logger.info("Start building lookup for existing clients")
            existing_ruts = _fetch_existing_values(conn)
            logger.info("Loaded %d existing client RUTs", len(existing_ruts))
            # Normaliza y filtra los RUTs válidos desde la BD
            rut_set = set(
                rut.replace(".", "").replace(" ", "").upper()
                for rut in existing_ruts
                if is_valid_rut(rut)
            )
            logger.info("Built normalized rut_set with %d entries", len(rut_set))

            # Filtra solo los RUTs nuevos, normalizados
            logger.info("Filtering new RUTs for insertion")
            df_to_insert = df_out.filter(
                ~pl.col("rut_cliente").map_elements(
                    lambda r: is_valid_rut(r) and r.replace(".", "").replace(" ", "").upper() in rut_set,
                    return_dtype=pl.Boolean
                )
            )
            logger.info("Rows to insert: %d", df_to_insert.height)
            if df_to_insert.is_empty():
                logger.info("No new clients to insert.")
                conn.rollback()
                raise NoNewDataError("No new clients to insert - process aborted.")

            placeholders = ", ".join(["?"] * len(df_to_insert.columns))
            insert_sql = (
                "INSERT INTO dbo.Cliente (" + ", ".join(df_to_insert.columns) + ") VALUES (" + placeholders + ")"
            )
            cur.fast_executemany = True
            cur.executemany(insert_sql, df_to_insert.to_numpy().tolist())
            conn.commit()
            logger.info("Inserted %d new clients into dbo.Cliente", df_to_insert.height)
        except Exception as e:
            logger.exception("Error inserting clients into dbo.Cliente: %s", e)
            conn.rollback()
            raise
        finally:
            cur.close()

###############################################################################
# Upsert ACCOUNTS                                                             #
###############################################################################

def upsert_accounts(df_accounts: pl.DataFrame) -> None:
    """Insert *new* bank accounts into **dbo.Cuenta**."""

    conn_str = get_db_connection_string()
    with pyodbc.connect(conn_str, autocommit=False) as conn:
        try:
            cur = conn.cursor()

            cols_map = {
                "NUMERO DE CUENTA": "id_cuenta",
                "RUT": "rut_cliente",
                "TIPO CUENTA": "tipo_cuenta",
                "FECHA APERTURA CUENTA": "fecha_apertura",
                "SALDO MAXIMO REGISTRADO": "saldo_maximo_registrado",
                "VECES SALDO CERO": "veces_saldo_cero",
                "USO DE TARJETA MENSUALMENTE": "uso_tarjeta_mensual",
            }

            # Validate expected columns
            missing_cols = [c for c in cols_map if c not in df_accounts.columns]
            if missing_cols:
                raise ValueError(f"Columns not present in accounts DataFrame: {missing_cols}")

            df_out = df_accounts.select(list(cols_map.keys())).rename(cols_map)

            # Cast numeric columns (all ints → safe for fast_executemany)
            df_out = df_out.with_columns(
                [
                    pl.col("id_cuenta").cast(pl.Int64),
                    pl.col("saldo_maximo_registrado").cast(pl.Int64),
                    pl.col("veces_saldo_cero").cast(pl.Int64),
                    pl.col("uso_tarjeta_mensual").cast(pl.Int64),
                ]
            )

            existing_ids = _fetch_existing_account_ids(conn)
            existing_ids_s = pl.Series(list(existing_ids), dtype=pl.Int64)
            df_to_insert = df_out.filter(~pl.col("id_cuenta").is_in(existing_ids_s))
            if df_to_insert.is_empty():
                logger.info("No new accounts to insert.")
                conn.rollback()
                raise NoNewDataError("No new accounts to insert - process aborted.")

            placeholders = ", ".join(["?"] * len(df_to_insert.columns))
            insert_sql = "INSERT INTO dbo.Cuenta (" + ", ".join(df_to_insert.columns) + ") VALUES (" + placeholders + ")"
            cur.fast_executemany = False  # safe: only ints & strings
            cur.executemany(insert_sql, df_to_insert.rows())
            conn.commit()
            logger.info("Inserted %d new accounts into dbo.Cuenta", df_to_insert.height)
        except Exception as e:
            logger.error("Error inserting accounts: %s", e)
            conn.rollback()
            raise
        finally:
            cur.close()

__all__ = [
    "upsert_clients",
    "upsert_accounts",
]
