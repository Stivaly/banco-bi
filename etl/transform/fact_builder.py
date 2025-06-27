from __future__ import annotations

"""fact_builder.py
Construye un DataFrame con *claves naturales* (rut_cliente, id_region, fecha…)
para la tabla de hechos **fact_cuenta** del DW.

Flujo general
-------------
1. Lee las tablas *Cliente* y *Cuenta* del OLTP (TransactBanco) usando la
   cadena devuelta por ``config.get_db_connection_string``.
2. Une ambas por ``rut_cliente``.
3. Calcula los **campos derivados**:
   • ``movimientos_mensuales``  ←  cantidad_contactos.
   • ``edad``                   ←  años cumplidos hoy (no se carga, pero útil si lo necesitas).
   • ``probabilidad_fuga``      ←  porcentaje 0-100 usando la ponderación 25/20/20/20/15.
4. Devuelve el DF con las columnas **exactas** que espera
   ``load_to_dw.insert_fact_cuenta`` (en ese orden):

    rut_cliente, id_region, fecha, tipo_cuenta,
    saldo_maximo, veces_saldo_cero, uso_tarjeta_mensual,
    movimientos_mensuales, probabilidad_fuga

"""

from datetime import date
from typing import Final

import polars as pl
from polars import Decimal
import pyodbc

from etl.config import get_db_connection_string
from etl.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constantes de ponderación
# ---------------------------------------------------------------------------
WEIGHTS: Final[dict[str, float]] = {
    "score_uso": 0.25,
    "score_cero": 0.20,
    "score_saldo": 0.20,
    "score_satisfaccion": 0.20,
    "score_ingreso": 0.15,
}

# ---------------------------------------------------------------------------
# Función pública
# ---------------------------------------------------------------------------

def build_fact_cuenta_df() -> pl.DataFrame:
    """Lee el OLTP y devuelve el DataFrame con naturalezas + métricas."""

    logger.info("Building fact_cuenta natural-key DataFrame from OLTP...")
    # 1) Leer datos del OLTP -------------------------------------------------
    query = """
    SELECT
        c.rut_cliente,
        c.region_id           AS id_region,
        cu.fecha_apertura     AS fecha,
        cu.tipo_cuenta,
        cu.saldo_maximo_registrado AS saldo_maximo,
        cu.veces_saldo_cero,
        cu.uso_tarjeta_mensual,
        c.cantidad_contactos      AS movimientos_mensuales,
        c.puntuacion_promedio     AS puntuacion_promedio,
        c.ingreso_mensual_promedio AS ingreso_mensual_promedio,
        c.fecha_nacimiento
    FROM dbo.Cuenta  cu
    JOIN dbo.Cliente c ON cu.rut_cliente = c.rut_cliente;
    """

    conn = pyodbc.connect(get_db_connection_string())
    try:
        df = pl.read_database(query, conn).with_columns([
            pl.col("puntuacion_promedio").cast(pl.Float64),
            pl.col("ingreso_mensual_promedio").cast(pl.Float64),
            pl.col("saldo_maximo").cast(pl.Float64),
        ])
    finally:
        conn.close()

    if df.is_empty():
        logger.warning("No rows returned from OLTP - fact_cuenta load skipped.")
        return df  

    today = date.today()

    df = df.with_columns([
        # Edad en años (por si lo necesitas en la dimensión)
        ((pl.lit(today) - pl.col("fecha_nacimiento")).dt.total_days() / 365.25)
            .floor()
            .cast(pl.Int64)
            .alias("edad"),

        # Scores normalizados 0‑1 -----------------------------------------
        # Evitamos división por 0 con .when(max==0).then(0) …
        ]).with_columns([
        (pl.when(pl.col("uso_tarjeta_mensual") == 0)
            .then(0)
            .otherwise(pl.col("uso_tarjeta_mensual")))
            .alias("_uso_tmp"),
        ])

    # Máximos para normalización -------------------------------------------
    max_vals = {
        "uso_tarjeta": df["_uso_tmp"].max() or 1,
        "saldo_cero":  df["veces_saldo_cero"].max() or 1,
        "saldo_max":   df["saldo_maximo"].max() or 1,
        "ingreso":     df["ingreso_mensual_promedio"].max() or 1,
    }

    df = df.with_columns([
        # Uso tarjeta (más alto = más riesgo)
        (pl.col("_uso_tmp") / max_vals["uso_tarjeta"]).alias("score_uso"),

        # Veces saldo cero (más alto = más riesgo)
        (pl.col("veces_saldo_cero") / max_vals["saldo_cero"])
            .fill_null(0)
            .alias("score_cero"),

        # Saldo máximo (menor saldo ⇒ mayor riesgo)
        pl.when((1 - (pl.col("saldo_maximo") / max_vals["saldo_max"])) < 0)
        .then(0)
        .otherwise(1 - (pl.col("saldo_maximo") / max_vals["saldo_max"]))
        .alias("score_saldo"),

        # Satisfacción (menor puntaje ⇒ mayor riesgo)
        pl.when((1 - (pl.col("puntuacion_promedio") / 5.0)) < 0)
        .then(0)
        .otherwise(1 - (pl.col("puntuacion_promedio") / 5.0))
        .alias("score_satisfaccion"),

        # Ingreso (menor ingreso ⇒ mayor riesgo)
        pl.when((1 - (pl.col("ingreso_mensual_promedio") / max_vals["ingreso"])) < 0)
        .then(0)
        .otherwise(1 - (pl.col("ingreso_mensual_promedio") / max_vals["ingreso"]))
        .alias("score_ingreso"),
    ])

    # 3) Probabilidad de fuga ----------------------------------------------
    expr = sum(WEIGHTS[k] * pl.col(k) for k in WEIGHTS)
    df = df.with_columns([
        (expr * 100)
        .round(2)
        .cast(pl.Float64)
        .alias("probabilidad_fuga")
    ])

    # 4) Seleccionar columnas finales --------------------------------------
    out = df.select([
        "rut_cliente", "id_region", "fecha", "tipo_cuenta",
        "saldo_maximo", "veces_saldo_cero", "uso_tarjeta_mensual",
        "movimientos_mensuales", "probabilidad_fuga",
    ])

    logger.info("fact_cuenta DataFrame listo: %d filas", out.height)
    return out

__all__ = ["build_fact_cuenta_df"]
