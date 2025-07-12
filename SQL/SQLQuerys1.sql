BEGIN TRANSACTION

USE staging;
GO

CREATE USER etl_app_user FOR LOGIN etl_app_user;

ALTER ROLE db_datareader ADD MEMBER etl_app_user;
ALTER ROLE db_datawriter ADD MEMBER etl_app_user;
ALTER ROLE db_ddladmin ADD MEMBER etl_app_user;

CREATE LOGIN etl_app_user WITH PASSWORD = '******';

COMMIT;

SELECT name FROM sys.databases;

SELECT name FROM sys.sql_logins;

SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'DatosCasoEstudio';

SELECT * FROM staging.DatosCasoEstudio;

BEGIN TRANSACTION
TRUNCATE TABLE staging.DatosCasoEstudio;
commit;

BEGIN TRANSACTION
TRUNCATE TABLE TransactBanco.dbo.Cliente;
commit;


USE TransactBanco;
GO

BEGIN TRAN;

MERGE dbo.Region AS tgt
USING (VALUES
    (1,  N'Arica Y Parinacota'),
    (2,  N'Tarapaca'),
    (3,  N'Antofagasta'),
    (4,  N'Atacama'),
    (5,  N'Coquimbo'),
    (6,  N'Valparaiso'),
    (7,  N'Metropolitana De Santiago'),
    (8,  N'Libertador General Bernardo O''Higgins'),
    (9,  N'Maule'),
    (10, N'Nuble'),
    (11, N'Biobio'),
    (12, N'La Araucania'),
    (13, N'Los Rios'),
    (14, N'Los Lagos'),
    (15, N'Aysen del General Carlos Iba�ez del Campo'),
    (16, N'Magallanes y de la Antartica Chilena')
) AS src(id_region, nombre_region)
ON  tgt.id_region      = src.id_region
    OR tgt.nombre_region = src.nombre_region
WHEN NOT MATCHED BY TARGET THEN
    INSERT (id_region, nombre_region)
    VALUES (src.id_region, src.nombre_region);

COMMIT;

SELECT * FROM TransactBanco.dbo.Cliente;