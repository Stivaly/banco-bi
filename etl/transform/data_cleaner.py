# etl/transform/data_cleaner.py
import re, unicodedata
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Set

import polars as pl
from etl.utils.logger import get_logger

log = get_logger(__name__)

# ─────────────────────────── Helpers ────────────────────────────
RUT_REGEX = re.compile(r"^\d{7,8}-[\dK]$", re.I)

def strip_accents(val: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", val)
                   if unicodedata.category(c) != "Mn")

def normalize_string(val: str | None) -> str | None:
    if val is None:
        return None
    return strip_accents(val.strip()).title()

def parse_date(val: str | date | None) -> date | None:
    if val is None or val == "":
        return None
    if isinstance(val, date):
        return val
    val = val.strip()
    if re.fullmatch(r"\d{8}", val):
        val = f"{val[:2]}/{val[2:4]}/{val[4:]}"
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    return None

def round_to_int(val) -> Decimal:
    return Decimal(val).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

def is_valid_rut(rut: str, base8: bool = False) -> bool:
    if not rut: return False
    rut = rut.replace(".", "").upper()
    if not RUT_REGEX.match(rut):
        return False
    digits, ver = rut.split("-")
    mult = [2,3,4,5,6,7,8] if base8 else [2,3,4,5,6,7]
    s = sum(int(d) * mult[i % len(mult)]
            for i, d in enumerate(reversed(digits)))
    mod = 11 - s % 11
    expected = "K" if mod == 10 else "0" if mod == 11 else str(mod)
    return ver == expected

def fail_if(df: pl.DataFrame, message: str):
    if df.height:
        log.error(message)
        log.debug(df)
        raise ValueError(message)

# ─────────────────────────── Look-ups ───────────────────────────
SEX_ALLOWED = {"M", "F"}  
SEX_MAP = {
    **{normalize_string(k): "M" for k in ("M", "Masculino", "Male", "Hombre")},
    **{normalize_string(k): "F" for k in ("F", "Femenino", "Female", "Mujer")},
}
EDU_ALLOWED: Set[str] = {
    "Educ. Tecnica", "Educ. Universitaria", "Educ. Media",
    "Estudiante Universitario", "Sin Informacion",
}
CIVIL_ALLOWED = {"Casado", "Separado", "Soltero", "Viudo"}
JOB_ALLOWED   = {"Dependiente", "Empresario", "Sin Informacion"}
ACCOUNT_TYPE_MAP = {
    "Cuenta Corriente": "Corriente",
    "Corriente": "Corriente",
    "Vista": "Vista",
}

OFFICIAL_REGIONS = {
    "Arica Y Parinacota", "Tarapaca", "Antofagasta", "Atacama", "Coquimbo",
    "Valparaiso", "Metropolitana De Santiago", "Libertador General Bernardo O'Higgins", "Maule",
    "Nuble", "Biobio", "La Araucania", "Los Rios", "Los Lagos",
    "Aysen del General Carlos Ibañez del Campo", "Magallanes y de la Antartica Chilena"
}
REGION_ALIAS = {normalize_string(r): r for r in OFFICIAL_REGIONS}  # amplía si llegan variantes
DECIMAL_3_2 = pl.Decimal(precision=3, scale=2)
# ─────────────────────── Transformation steps ───────────────────
def transform_clients(df: pl.DataFrame) -> pl.DataFrame:
    log.info("Transforming clients DataFrame...")
    out = (df.with_columns([
        pl.col("SEXO").map_elements(                  
            lambda s: SEX_MAP.get(normalize_string(s), None),
            return_dtype=pl.Utf8
        ),
        pl.col("NIVEL EDUCACIONAL DECLARADO").map_elements(
            normalize_string, return_dtype=pl.Utf8
        ),
        pl.col("ESTADO CIVIL").map_elements(
            normalize_string, return_dtype=pl.Utf8
        ),
        pl.col("ACTIVIDAD").map_elements(
            normalize_string, return_dtype=pl.Utf8
        ),
        pl.col("FECHA DE NACIMIENTO").map_elements(
            parse_date, return_dtype=pl.Date
        ),
        pl.col("INGRESO MENSUAL PROMEDIO").map_elements(
            lambda v: round_to_int(v) if v is not None else None,
            return_dtype=pl.Decimal
        ),
        pl.col("PUNTUACIÓN PROMEDIO")
          .map_elements(lambda x: round(float(x), 2) if x is not None else None,
                        return_dtype=pl.Float64)    
          .cast(DECIMAL_3_2)                        
          .alias("PUNTUACIÓN PROMEDIO"),
        pl.col("TOTAL DE CONTACTOS").cast(pl.Int64),
    ]))
    log.debug(f"Clients DF after transform: {out.head()}")
    return out

def transform_accounts(df: pl.DataFrame) -> pl.DataFrame:
    log.info("Transforming accounts DataFrame...")
    out = (df
        .with_columns([
            pl.col("TIPO CUENTA").map_elements(
                lambda x: ACCOUNT_TYPE_MAP.get(normalize_string(x), None),
                return_dtype=pl.Utf8
            ),
            pl.col("FECHA APERTURA CUENTA").map_elements(
                parse_date,
                return_dtype=pl.Date
            ),
            pl.col("SALDO MAXIMO REGISTRADO").cast(pl.Decimal),
            pl.col("VECES SALDO CERO").cast(pl.Int64),
            pl.col("USO DE TARJETA MENSUALMENTE").cast(pl.Int64),
        ]))
    log.debug(f"Accounts DF after transform: {out.head()}")
    return out

def transform_regions(df: pl.DataFrame) -> pl.DataFrame:
    log.info("Transforming regions DataFrame...")
    if "REGIÓN" not in df.columns and "Region" in df.columns:
        df = df.rename({"Region": "REGIÓN"})
    out = df.with_columns([
            pl.col("REGIÓN").alias("REGIÓN_ORIG"),                       
            pl.col("REGIÓN").map_elements(
                lambda x: REGION_ALIAS.get(normalize_string(x), None),
                return_dtype=pl.Utf8
            ).alias("REGIÓN")
        ])
    log.debug(f"Regions DF after transform: {out.head()}")
    return out

# ─────────────────────────── Validations ─────────────────────────
def validate_clients(df: pl.DataFrame, base8: bool = False):
    log.info("Validating clients DataFrame...")
    today = date.today()
    age_days_expr = (pl.lit(today) - pl.col("FECHA DE NACIMIENTO")).dt.total_days()
    fail_if(
        df.filter(
            ~pl.col("RUT").map_elements(
                lambda r: is_valid_rut(r, base8),
                return_dtype=pl.Boolean
            )
        ),
            "RUT inválido"
    )
    fail_if(df.filter(
        (pl.col("FECHA DE NACIMIENTO").is_null()) |
        (pl.col("FECHA DE NACIMIENTO") > pl.lit(today)) |
        (age_days_expr < 14 * 365),
    ),
    "Fecha de nacimiento fuera de rango")
    for col, dom in [
        ("SEXO", SEX_ALLOWED),
        ("NIVEL EDUCACIONAL DECLARADO", EDU_ALLOWED),
        ("ESTADO CIVIL", CIVIL_ALLOWED),
        ("ACTIVIDAD", JOB_ALLOWED),
    ]:
        fail_if(df.filter(~pl.col(col).is_in(dom)),
                f"{col} fuera de dominio")
    fail_if(df.filter(pl.col("INGRESO MENSUAL PROMEDIO") < 0),
            "Ingreso mensual negativo")
    fail_if(df.filter(~((pl.col("PUNTUACIÓN PROMEDIO") >= 0.00) &
                        (pl.col("PUNTUACIÓN PROMEDIO") <= 5.00))),
            "Puntuación fuera de rango")
    fail_if(df.filter(pl.col("TOTAL DE CONTACTOS") < 0),
            "Contactos negativos")
    log.info("Clients DataFrame passed validation.")

def validate_accounts(df: pl.DataFrame):
    log.info("Validating accounts DataFrame...")
    today = date.today()
    fail_if(df.filter(pl.col("TIPO CUENTA").is_null()), "Tipo cuenta inválido")
    fail_if(df.filter(
        (pl.col("FECHA APERTURA CUENTA").is_null()) |
        (pl.col("FECHA APERTURA CUENTA") < date(1950,1,1)) |
        (pl.col("FECHA APERTURA CUENTA") > today)),
        "Fecha apertura fuera de rango")
    fail_if(df.filter(pl.col("SALDO MAXIMO REGISTRADO") < 0),
            "Saldo máximo negativo")
    fail_if(df.filter(pl.col("VECES SALDO CERO") < 0),
            "Veces saldo cero negativo")
    fail_if(df.filter(pl.col("USO DE TARJETA MENSUALMENTE") < 0),
            "Uso tarjeta mensual negativo")
    log.info("Accounts DataFrame passed validation.")

def validate_regions(df: pl.DataFrame):
    log.info("Validating regions DataFrame...")
    
    invalid = df.filter(pl.col("REGIÓN").is_null())
    fail_if(
        invalid,
        f"Región no oficial: {invalid['REGIÓN_ORIG'].unique().to_list()}"
    )
    log.info("Regions DataFrame passed validation.")

# ─────────────────────── Public entry points ────────────────────
def clean_clients(raw_df: pl.DataFrame, base8: bool = False) -> pl.DataFrame:
    log.info("Cleaning clients data...")
    df = transform_clients(raw_df)
    validate_clients(df, base8)
    return df

def clean_accounts(raw_df: pl.DataFrame) -> pl.DataFrame:
    log.info("Cleaning accounts data...")
    df = transform_accounts(raw_df)
    validate_accounts(df)
    return df

def clean_regions(raw_df: pl.DataFrame) -> pl.DataFrame:
    log.info("Cleaning regions data...")
    df = transform_regions(raw_df)
    validate_regions(df)
    return df
