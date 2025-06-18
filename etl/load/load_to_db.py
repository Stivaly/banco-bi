# etl/load/load_to_db.py – client & account upserts with robust region handling
# --------------------------------------------------------------------------
# ▸ upsert_clients(df_clients): Inserta clientes nuevos asegurando region_id
# ▸ upsert_accounts(df_accounts): Inserta cuentas nuevas coherentes con la FK
# Ambos DataFrames llegan transformados pero SIN renombrar columnas: usamos
# los encabezados originales del Excel como claves del mapa.

import csv
import os
from typing import List, Set, Dict

import pyodbc
import polars as pl

from etl.transform.data_cleaner import normalize_string
from etl.config import get_db_connection_string
from etl.utils.logger import get_logger

logger = get_logger(__name__)

###############################################################################
# Helper utilities                                                             #
###############################################################################

def _fetch_existing_values(conn: pyodbc.Connection, base_query: str, values: List) -> Set:
    """Return the subset of *values* that already exist in the table."""
    if not values:
        return set()

    placeholders = ",".join(["?"] * len(values))
    query = f"{base_query} IN ({placeholders})"
    with conn.cursor() as cur:
        cur.execute(query, values)
        return {row[0] for row in cur.fetchall()}

###############################################################################
# Region helpers (fallback only for clientes)                                  #
###############################################################################

def _build_region_lookup(cur: pyodbc.Cursor) -> Dict[str, int]:
    """region → id_region (raw y normalizado)"""
    cur.execute("SELECT id_region, nombre_region FROM dbo.Region")
    lookup: Dict[str, int] = {}
    for id_region, nombre_region in cur.fetchall():
        raw = nombre_region.strip().lower()
        lookup[raw] = id_region
        lookup[normalize_string(raw)] = id_region
    return lookup


def _ensure_region_column(df: pl.DataFrame) -> pl.DataFrame:
    """Asegura columna 'Region' (desde 'REGIÓN' si hace falta)."""
    if "Region" in df.columns:
        return df
    if "REGIÓN" in df.columns:
        return df.with_columns(pl.col("REGIÓN").alias("Region"))
    return df


def _fallback_map_id_region(df: pl.DataFrame, lookup: Dict[str, int]) -> pl.DataFrame:
    df = _ensure_region_column(df)
    if "Region" not in df.columns:
        raise ValueError("Cannot map region: 'Region' column not present in DataFrame")

    def _lk(name: str):
        if name is None:
            return None
        key = name.strip().lower()
        return lookup.get(key) or lookup.get(normalize_string(key))

    return df.with_columns(
        pl.col("Region").map_elements(_lk, return_dtype=pl.Int64).alias("id_region")
    )


def _export_problem_rows(df_missing: pl.DataFrame, label: str) -> None:
    if df_missing.height == 0:
        return

    rut_col = "RUT" if "RUT" in df_missing.columns else "rut_cliente"
    region_col = "Region" if "Region" in df_missing.columns else ("REGIÓN" if "REGIÓN" in df_missing.columns else None)
    cols = [rut_col] + ([region_col] if region_col else [])

    fname = f"missing_region_{label}.csv"
    with open(fname, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(cols)
        writer.writerows(df_missing.select(cols).rows())
    logger.warning("%d rows skipped – región no encontrada. Detalles: %s", df_missing.height, os.path.abspath(fname))

###############################################################################
# Upsert CLIENTES                                                              #
###############################################################################

def upsert_clients(df_clients: pl.DataFrame) -> None:
    conn_str = get_db_connection_string()
    with pyodbc.connect(conn_str, autocommit=False) as conn:
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
            logger.info("No valid client rows to insert after region check – aborting.")
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

        existing_ruts = _fetch_existing_values(
            conn,
            "SELECT rut_cliente FROM dbo.Cliente WHERE rut_cliente",
            df_out["rut_cliente"].to_list(),
        )
        df_to_insert = df_out.filter(~pl.col("rut_cliente").is_in(existing_ruts))
        if df_to_insert.is_empty():
            logger.info("No new clients to insert.")
            return

        placeholders = ", ".join(["?"] * len(df_to_insert.columns))
        insert_sql = (
            "INSERT INTO dbo.Cliente (" + ", ".join(df_to_insert.columns) + ") VALUES (" + placeholders + ")"
        )
        cur.fast_executemany = True
        cur.executemany(insert_sql, df_to_insert.to_numpy().tolist())
        conn.commit()
        logger.info("Inserted %d new clients into dbo.Cliente", df_to_insert.height)

###############################################################################
# Upsert CUENTAS                                                               #
###############################################################################

def upsert_accounts(df_accounts: pl.DataFrame) -> None:
    conn_str = get_db_connection_string()
    with pyodbc.connect(conn_str, autocommit=False) as conn:
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

        missing_cols = [c for c in cols_map if c not in df_accounts.columns]
        if missing_cols:
            raise ValueError(f"Columns not present in accounts DataFrame: {missing_cols}")

        df_out = df_accounts.select(list(cols_map.keys())).rename(cols_map)

        df_out = df_out.with_columns([
            pl.col("saldo_maximo_registrado").cast(pl.Int64),
            pl.col("veces_saldo_cero").cast(pl.Int64),
            pl.col("uso_tarjeta_mensual").cast(pl.Int64),
        ])

        existing_ids = _fetch_existing_values(
            conn,
            "SELECT id_cuenta FROM dbo.Cuenta WHERE id_cuenta",
            df_out["id_cuenta"].to_list(),
        )
        df_to_insert = df_out.filter(~pl.col("id_cuenta").is_in(existing_ids))
        if df_to_insert.is_empty():
            logger.info("No new accounts to insert.")
            return

        placeholders = ", ".join(["?"] * len(df_to_insert.columns))
        insert_sql = (
            "INSERT INTO dbo.Cuenta (" + ", ".join(df_to_insert.columns) + ") VALUES (" + placeholders + ")"
        )
        cur.fast_executemany = True
        cur.executemany(insert_sql, df_to_insert.to_numpy().tolist())
        conn.commit()
        logger.info("Inserted %d new accounts into dbo.Cuenta", df_to_insert.height)

__all__ = [
    "upsert_clients",
    "upsert_accounts",
]
