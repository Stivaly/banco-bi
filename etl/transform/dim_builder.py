from __future__ import annotations

"""dim_builder.py
Genera el DataFrame de **dim_cliente** con todos los atributos necesarios
(derivados incluidos) para poblar la dimensión en el DW.

Flujo:
-------
1. Lee la tabla **Cliente** del OLTP (TransactBanco) usando la cadena de
   conexión `config.get_db_connection_string()`.
2. Calcula las columnas derivadas:
   • `edad`  → años cumplidos hoy.
   • `rango_satisfaccion` → Baja, Media, Alta según `puntuacion_promedio`.
   • `segmento_educacional` (ejemplo: "Superior", "Técnica", "Media", "Sin Info").
3. Rellena metadata SCD tipo‑2: `valid_from`, `is_current`.
4. Devuelve un *Polars DataFrame* con las **mismas columnas** (y orden)
   de la tabla `dbo.dim_cliente`, *except* la surrogate `cliente_key`.

El upsert/merge a la dimensión se hará en `dim_loaders.upsert_dim_cliente`.
"""

from datetime import date

import polars as pl
import pyodbc

from etl.transform.data_cleaner import parse_date
from etl.config import get_db_connection_string
from etl.utils.logger import get_logger

logger = get_logger(__name__)

_EDU_SEGMENT_MAP = {
    "Educ. Universitaria": "Superior",
    "Estudiante Universitario": "Superior",
    "Educ. Tecnica": "Tecnica",
    "Educ. Media": "Media",
    "Sin Informacion": "Sin Info",
}

def _compute_age(birth: pl.Expr) -> pl.Expr:
    """Años cumplidos al día de hoy (int)."""
    today = date.today()
    return ((pl.lit(today) - birth).dt.total_days() / 365.25).floor().cast(pl.Int64)


def _compute_satisfaction(score: pl.Expr) -> pl.Expr:
    """Clasifica la puntuación promedio en Baja, Media, Alta."""
    return (
        pl.when(score < 3).then(pl.lit("Baja"))
          .when(score < 4).then(pl.lit("Media"))
          .otherwise(pl.lit("Alta"))
    )


def _map_segmento_edu(level: pl.Expr) -> pl.Expr:
    return level.map_elements(lambda x: _EDU_SEGMENT_MAP.get(x, None), return_dtype=pl.Utf8)

def build_dim_cliente_df() -> pl.DataFrame:
    """Lee *Cliente* y devuelve un DataFrame apto para dim_cliente."""

    sql = """
    SELECT
        rut_cliente,
        fecha_nacimiento,
        nivel_educacional,
        sexo,
        estado_civil,
        actividad,
        ingreso_mensual_promedio,
        puntuacion_promedio,
        cantidad_contactos,
        region_id
    FROM dbo.Cliente;"""

    logger.info("Reading Cliente from OLTP …")
    with pyodbc.connect(get_db_connection_string()) as conn:
        df = pl.read_database(sql, conn)
    logger.info("Fetched %d customer rows", df.height)
        
    if df.is_empty():
        logger.warning("Cliente table returned no rows - dim DataFrame is empty.")
        return df

    today = date.today()

    df = (
        df.with_columns([
            _compute_age(pl.col("fecha_nacimiento")).alias("edad"),
            _compute_satisfaction(pl.col("puntuacion_promedio")).alias("rango_satisfaccion"),
            _map_segmento_edu(pl.col("nivel_educacional")).alias("segmento_educacional"),
            pl.lit(today).alias("valid_from"),
            pl.lit(None).cast(pl.Date).alias("valid_to"),
            pl.lit(1).cast(pl.Int64).alias("is_current"),
        ])
    )

    df = df.rename({
        "ingreso_mensual_promedio": "ingreso_mensual",
        "puntuacion_promedio": "puntuacion_prom"
    })

    required_not_null = [
        "rut_cliente", "fecha_nacimiento", "nivel_educacional", "sexo",
        "estado_civil", "actividad", "ingreso_mensual", "puntuacion_prom",
        "cantidad_contactos", "edad", "rango_satisfaccion", "segmento_educacional"
    ]

    for col in required_not_null:
        if df.filter(pl.col(col).is_null()).height > 0:
            raise ValueError(f"Null detectado en columna '{col}'. Detenida la inserción a dim_cliente.")

    ordered_cols = [
        "rut_cliente", "fecha_nacimiento", "nivel_educacional", "sexo",
        "estado_civil", "actividad", "ingreso_mensual",  
        "puntuacion_prom",                               
        "cantidad_contactos", "rango_satisfaccion",
        "edad", "segmento_educacional", "valid_from", "valid_to", "is_current",
    ]

    return df.select(ordered_cols)


__all__ = ["build_dim_cliente_df"]
