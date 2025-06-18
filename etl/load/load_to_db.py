import pyodbc, polars as pl
from etl.transform.data_cleaner import normalize_string
from etl.config import get_db_connection_string
from etl.utils.logger import get_logger
logger = get_logger(__name__)

def _fetch_existing_values(conn, base_query: str, values: list[str]) -> set[str]:
    """
    Ejecuta SELECT ... WHERE col IN (<placeholders>) 
    devolviendo un set de valores ya existentes.

    • Si values está vacío, devuelve set() y no lanza consulta.
    • Genera dinámica­mente los placeholders ?,?,? según la cantidad.
    """
    if not values:
        return set()

    placeholders = ",".join("?" * len(values))
    query = base_query.format(placeholders)        
    cur = conn.cursor()
    cur.execute(query, values)                    
    return {row[0] for row in cur.fetchall()}

def upsert_clients(df: pl.DataFrame) -> None:
    CLIENT_COL_MAP = {
        "Rut"                       : "rut_cliente",
        "Fecha De Nacimiento"       : "fecha_nacimiento",
        "Nivel Educacional Declarado": "nivel_educacional",
        "Sexo"                      : "sexo",
        "Estado Civil"              : "estado_civil",
        "Actividad"                 : "actividad",
        "Ingreso Mensual Promedio"  : "ingreso_mensual_promedio",
        "Puntuacion Promedio"       : "puntuacion_promedio",
        "Total De Contactos"        : "cantidad_contactos",
        "id_region"                 : "region_id",
    }
    conn = pyodbc.connect(get_db_connection_string(), autocommit=True)
    cur  = conn.cursor()

    existing = _fetch_existing_values(
        conn,
        "SELECT rut_cliente FROM dbo.Cliente WHERE rut_cliente IN ({})",
        df["RUT"].to_list()
    )
    new_df = (df.filter(~pl.col("RUT").is_in(existing))
                .rename({c: normalize_string(c) for c in df.columns}))
    if new_df.is_empty():
        logger.info("No new clients to insert.")
        cur.close(); conn.close()
        return

    cur.execute("SELECT id_region, nombre_region FROM dbo.Region;")
    region_map = {row[1]: row[0] for row in cur.fetchall()}

    new_df = (new_df
        .with_columns(
            pl.col("Region").map_elements(
                lambda n: region_map.get(n), 
                return_dtype=pl.Int64
            ).alias("id_region")
        )
        .drop("Region")
    )
    logger.info(f"Cols originales Cliente despues de map: {new_df.columns}")
    new_df = new_df.select(list(CLIENT_COL_MAP.keys()))
    new_df = new_df.rename(CLIENT_COL_MAP)
    
    cols = list(new_df.columns)          
    placeholders = ",".join("?" * len(cols))
    cols_sql      = ",".join(f"[{c}]" for c in cols) 

    cur.executemany(
        f"INSERT INTO dbo.Cliente ({(cols_sql)}) VALUES ({placeholders})",
        new_df.rows()
    )
    logger.info(f"Inserted {new_df.height} new clients.")

    cur.close(); conn.close()

def upsert_accounts(df: pl.DataFrame):
    
    conn = pyodbc.connect(get_db_connection_string(), autocommit=True)
    existing = _fetch_existing_values(
        conn,
        "SELECT id_cuenta FROM dbo.Cuenta WHERE id_cuenta IN ({})",
        df["NUMERO DE CUENTA"].to_list()
    )
    new_df = df.filter(~pl.col("NUMERO DE CUENTA").is_in(existing))
    new_df = new_df.rename({c: normalize_string(c) for c in new_df.columns})
    if new_df.height:
        cols_map = {
            "Numero De Cuenta"           : "id_cuenta",
            "Rut"                        : "rut_cliente",
            "Tipo Cuenta"                : "tipo_cuenta",
            "Fecha Apertura Cuenta"      : "fecha_apertura",
            "Saldo Maximo Registrado"    : "saldo_maximo_registrado",
            "Veces Saldo Cero"           : "veces_saldo_cero",
            "Uso De Tarjeta Mensualmente": "uso_tarjeta_mensual",
        }
        new_df = new_df.rename(cols_map)
        
        cols = list(new_df.columns)  
        placeholders = ",".join(["?"]*len(new_df.columns))
        cols_sql      = ",".join(f"[{c}]" for c in cols) 
        conn.cursor().executemany(
            f"INSERT INTO dbo.Cuenta ({cols_sql}) VALUES ({placeholders})",
            new_df.rows()
        )
        logger.info(f"Inserted {new_df.height} cuentas nuevas")
    conn.close()

