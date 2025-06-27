from typing import Dict
import polars as pl
import pyodbc
from etl.utils.logger import get_logger
from etl.config import get_dwh_connection_string, get_db_connection_string

logger = get_logger(__name__)


def _fetch_existing(conn, table: str, nat_col: str, sur_col: str) -> pl.DataFrame:
    query = f"SELECT {nat_col}, {sur_col} FROM {table}"
    df = pl.read_database(query, conn)
    if df.schema[nat_col] == pl.Utf8:
        df = df.with_columns(pl.col(nat_col).cast(str))
    return df


def _insert_new_rows(
    conn,
    df_new: pl.DataFrame,
    table: str,
    nat_cols: list[str]
) -> None:
    if df_new.is_empty():
        return
    placeholders = ", ".join(["?"] * len(nat_cols))
    cols_sql = ", ".join(nat_cols)
    sql = f"INSERT INTO {table} ({cols_sql}) VALUES ({placeholders})"
    logger.info("Inserting %d new rows into %s", df_new.height, table)
    with conn.cursor() as cur:
        cur.fast_executemany = True
        cur.executemany(sql, df_new.select(nat_cols).rows())
        conn.commit()


def upsert_dim_cliente(df: pl.DataFrame) -> Dict[str, int]:
    """Ensure dim_cliente contains every RUT in df and return mapping."""
    table = "dbo.dim_cliente"
    nat_col, sur_col = "rut_cliente", "cliente_key"
    dim_cols = [
        "rut_cliente", "fecha_nacimiento", "nivel_educacional", "sexo",
        "estado_civil", "actividad", "ingreso_mensual", "puntuacion_prom",
        "cantidad_contactos", "edad", "rango_satisfaccion", "segmento_educacional",
        "valid_from", "valid_to", "is_current"
    ]
    with pyodbc.connect(get_dwh_connection_string()) as conn:
        existing = _fetch_existing(conn, "dbo.dim_cliente", nat_col, sur_col)
        existing = existing.with_columns(pl.col(nat_col).cast(str))
        missing = (
            df.select(nat_col)
            .unique()
            .filter(~pl.col(nat_col).is_in(existing[nat_col]))
        )

        if missing.is_empty():
            logger.info("upsert_dim_cliente: no hay nuevos clientes – inserción omitida.")
            return dict(zip(existing[nat_col].to_list(), existing[sur_col].to_list()))

        new_df = df.filter(pl.col(nat_col).is_in(missing[nat_col]))

        _insert_new_rows(conn, new_df, table, dim_cols)

        full = _fetch_existing(conn, table, nat_col, sur_col)

    return dict(zip(full[nat_col].to_list(), full[sur_col].to_list()))


def upsert_dim_region(df: pl.DataFrame) -> Dict[int, int]:
    """
    Inserta nuevas regiones en dim_region, buscando su nombre desde dbo.Region (OLTP).
    Devuelve {id_region → region_key}.
    """
    table, nat_col, sur_col = "dbo.dim_region", "id_region", "region_key"

    with pyodbc.connect(get_dwh_connection_string()) as dw_conn:
        existing = _fetch_existing(dw_conn, table, nat_col, sur_col)
        new_ids = (
            df.select(nat_col)
              .unique()
              .filter(~pl.col(nat_col).is_in(existing[nat_col]))
        )

        if new_ids.is_empty():
            logger.info("upsert_dim_region: no new regions – load skipped.")
            return dict(zip(existing[nat_col].to_list(), existing[sur_col].to_list()))

    # 2. Buscar los nombres desde OLTP
    region_ids = ", ".join(str(v) for v in new_ids[nat_col].to_list())
    lookup_sql = f"""
        SELECT id_region, nombre_region
        FROM dbo.Region
        WHERE id_region IN ({region_ids})
    """
    with pyodbc.connect(get_db_connection_string()) as db_conn:
        df_lookup = pl.read_database(lookup_sql, db_conn)

    if df_lookup.is_empty():
        raise ValueError("No se encontraron nombres para las nuevas regiones en dbo.Region.")

    # 3. Insertar en el DW
    with pyodbc.connect(get_dwh_connection_string()) as dw_conn:
        _insert_new_rows(dw_conn, df_lookup, table, ["id_region", "nombre_region"])
        full = _fetch_existing(dw_conn, table, nat_col, sur_col)

    return dict(zip(full[nat_col].to_list(), full[sur_col].to_list()))

def upsert_dim_time(df: pl.DataFrame) -> Dict[str, int]:
    """
    Build a {ISO-date-str → date_key} map, assuming dim_tiempo ya está pre-cargada
    con el calendario 1950-2035 (script del DW).
    """
    table, nat_col, sur_col = "dbo.dim_tiempo", "fecha", "date_key"

    with pyodbc.connect(get_dwh_connection_string()) as conn:
        mapping = _fetch_existing(conn, table, nat_col, sur_col)

    conn.close()
    return {str(dt): key for dt, key in zip(mapping[nat_col].to_list(),
                                            mapping[sur_col].to_list())}