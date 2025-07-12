IF DB_ID('BancoBI_DW') IS NOT NULL DROP DATABASE BancoBI_DW;
GO
CREATE DATABASE BancoBI_DW
 COLlate Modern_Spanish_CI_AS;              
GO
ALTER DATABASE BancoBI_DW SET RECOVERY SIMPLE;
GO
USE BancoBI_DW;
GO

/* =========================================================
   1. DIMENSIONES
   ========================================================= */

/* 1.1 Región ------------------------------------------------*/
CREATE TABLE dbo.dim_region (
    region_key   INT IDENTITY(1,1) PRIMARY KEY,
    id_region    INT          UNIQUE,      
    nombre_region VARCHAR(50) NOT NULL
);
CREATE INDEX IX_dim_region_nombre ON dbo.dim_region(nombre_region);

/* 1.2 Cliente ----------------------------------------------*/
CREATE TABLE dbo.dim_cliente (
    cliente_key          INT IDENTITY(1,1) PRIMARY KEY,
    rut_cliente          VARCHAR(12) UNIQUE,          
    fecha_nacimiento     DATE            NOT NULL,
    nivel_educacional    VARCHAR(50)     NOT NULL,
    sexo                 CHAR(1)         NOT NULL CHECK (sexo IN ('M','F')),
    estado_civil         VARCHAR(20)     NOT NULL,
    actividad            VARCHAR(100)    NOT NULL,
    ingreso_mensual      DECIMAL(10,2)   NOT NULL,
    puntuacion_prom      DECIMAL(3,2)    NOT NULL,
    cantidad_contactos   INT             NOT NULL DEFAULT 0,
    rango_satisfaccion   VARCHAR(20)     NULL,
    edad                 INT             NOT NULL,
    segmento_educacional VARCHAR(20)     NULL,
    valid_from           DATE            NOT NULL DEFAULT GETDATE(),
    valid_to             DATE            NULL,
    is_current           BIT             NOT NULL DEFAULT 1
);
CREATE INDEX IX_dim_cliente_rut ON dbo.dim_cliente(rut_cliente);

/* 1.3 Tiempo -----------------------------------------------*/
CREATE TABLE dbo.dim_tiempo (
    date_key    INT         PRIMARY KEY,           
    fecha       DATE UNIQUE,                      
    año         INT,
    semestre    INT,
    trimestre   INT,
    mes         INT,
    nombre_mes  VARCHAR(20)
);

-- 1.3.2 Rellena calendario 1950-2035
DECLARE @start DATE = '19500101',
        @end   DATE = '20351231';

;WITH cte AS (
    SELECT d = @start
    UNION ALL
    SELECT DATEADD(DAY,1,d) FROM cte WHERE d < @end
)
INSERT INTO dbo.dim_tiempo (date_key, fecha, año, semestre, trimestre, mes, nombre_mes)
SELECT  CONVERT(INT, FORMAT(d,'yyyyMMdd')),
        d,
        YEAR(d),
        (MONTH(d)+5)/6,           
        (MONTH(d)+2)/3,          
        MONTH(d),
        DATENAME(MONTH,d)
FROM cte OPTION (MAXRECURSION 0);

CREATE INDEX IX_dim_tiempo_anio_mes ON dbo.dim_tiempo(año, mes);

/* =========================================================
   2. TABLA DE HECHOS
   ========================================================= */
CREATE TABLE dbo.fact_cuenta (
    cuenta_key            INT IDENTITY(1,1),  
    cliente_key           INT            NOT NULL,
    region_key            INT            NOT NULL,
    date_key              INT            NOT NULL,
    tipo_cuenta           VARCHAR(50)    NOT NULL,
    saldo_maximo          DECIMAL(12,2)  NOT NULL,
    veces_saldo_cero      INT            NOT NULL DEFAULT 0,
    uso_tarjeta_mensual   INT            NOT NULL,
    movimientos_mensuales INT            NOT NULL,
    probabilidad_fuga     DECIMAL(5,2)   NOT NULL CHECK (probabilidad_fuga BETWEEN 0 AND 100),

    CONSTRAINT FK_fact_cliente FOREIGN KEY (cliente_key) REFERENCES dbo.dim_cliente(cliente_key),
    CONSTRAINT FK_fact_region  FOREIGN KEY (region_key)  REFERENCES dbo.dim_region(region_key),
    CONSTRAINT FK_fact_tiempo  FOREIGN KEY (date_key)    REFERENCES dbo.dim_tiempo(date_key)
);
/* Índice Columnstore para compresión y velocidad de lectura */
CREATE CLUSTERED COLUMNSTORE INDEX CCI_fact_cuenta ON dbo.fact_cuenta;

/* =========================================================
   3. ESQUEMA BÁSICO DE SEGURIDAD
   ========================================================= */
CREATE ROLE dw_readonly;
GRANT SELECT ON SCHEMA :: dbo    TO dw_readonly;   -- completo
GRANT VIEW DEFINITION            TO dw_readonly;   -- para SSAS

/* =========================================================
   4. METADATOS Y VERSIONADO
   ========================================================= */
EXEC sys.sp_addextendedproperty
     @name = N'DW_Version', @value = N'v1.0 – 2025-06-19 – BancoBI',
     @level0type = N'SCHEMA', @level0name = N'dbo';

/* permisos de usuario */

USE BancoBI_DW;
GO
CREATE USER etl_app_user FOR LOGIN etl_app_user;
ALTER ROLE db_datareader ADD MEMBER etl_app_user;
ALTER ROLE db_datawriter ADD MEMBER etl_app_user;
ALTER ROLE db_ddladmin ADD MEMBER etl_app_user;