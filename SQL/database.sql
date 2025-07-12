CREATE TABLE [Cliente] (
  [rut_cliente] varchar(12) PRIMARY KEY NOT NULL,
  [fecha_nacimiento] date NOT NULL CHECK (
    fecha_nacimiento <= DATEADD(year, -14, GETDATE()) 
    AND fecha_nacimiento >= '1920-01-01'              
  ),
  [nivel_educacional] varchar(50) CHECK (
    nivel_educacional IN ('EDUC. TÉCNICA', 'EDUC. UNIVERSITARIA', 'EDUC. MEDIA', 'ESTUDIANTE UNIVERSITARIO', 'SIN INFORMACION')
  ),
  [sexo] char(1) CHECK (sexo IN ('M', 'F')),
  [estado_civil] varchar(20) CHECK (estado_civil IN ('CASADO', 'SEPARADO', 'SOLTERO', 'VIUDO')),
  [actividad] varchar(100) CHECK (actividad IN ('DEPENDIENTE', 'EMPRESARIO', 'SIN INFORMACION')),
  [ingreso_mensual_promedio] decimal(10, 2) CHECK (ingreso_mensual_promedio >= 0),
  [puntuacion_promedio] decimal(3, 2) CHECK (puntuacion_promedio BETWEEN 1.00 AND 5.00),
  [cantidad_contactos] int CHECK (cantidad_contactos >= 0),
  [region_id] int
);
GO

CREATE TABLE [Cuenta] (
  [id_cuenta] int PRIMARY KEY NOT NULL,
  [rut_cliente] varchar(12),
  [tipo_cuenta] varchar(50) CHECK (tipo_cuenta IN ('CORRIENTE', 'VISTA')),
  [fecha_apertura] date NOT NULL CHECK (
    fecha_apertura BETWEEN '1950-01-01' AND GETDATE()
  ),
  [saldo_maximo_registrado] decimal(10,2) CHECK (saldo_maximo_registrado >= 0),
  [veces_saldo_cero] int CHECK (veces_saldo_cero >= 0),
  [uso_tarjeta_mensual] bit
);
GO

CREATE TABLE [Region] (
  [id_region] int PRIMARY KEY NOT NULL,
  [nombre_region] varchar(50) CHECK (
    nombre_region IN (
      'Arica y Parinacota', 'Tarapacá', 'Antofagasta', 'Atacama', 'Coquimbo', 
      'Valparaíso', 'Metropolitana de Santiago', 'Libertador General Bernardo O’Higgins', 
      'Maule', 'Ñuble', 'Biobío', 'La Araucanía', 'Los Ríos', 'Los Lagos', 
      'Aysén del General Carlos Ibáñez del Campo', 'Magallanes y de la Antártica Chilena'
    )
  )
);
GO


ALTER TABLE dbo.Region
DROP CONSTRAINT CK_Region_Nombre_Normalizado;   
GO

ALTER TABLE dbo.Region
ADD CONSTRAINT CK_Region_Nombre_Normalizado
CHECK ( nombre_region IN (
    'Arica y Parinacota', 'Tarapaca', 'Antofagasta', 'Atacama', 'Coquimbo',
    'Valparaiso', 'Metropolitana de Santiago', 'Libertador General Bernardo O''Higgins',
    'Maule', 'Nuble', 'Biobio', 'La Araucania', 'Los Rios', 'Los Lagos',
    'Aysen del General Carlos Ibañez del Campo', 'Magallanes y de la Antartica Chilena'
));
GO 

ALTER TABLE dbo.Cliente
DROP CONSTRAINT CK__Cliente__nivel_e__25869641;
GO

ALTER TABLE dbo.Cliente
ADD CONSTRAINT CK_Cliente_puntuacion_promedio
CHECK (puntuacion_promedio BETWEEN 0.00 AND 5.00);
GO

ALTER TABLE dbo.Cliente
ADD CONSTRAINT CK__Cliente__nivel_e__25869641
CHECK (nivel_educacional IN ('Educ. Tecnica', 'Educ. Universitaria', 'Educ. Media','Estudiante Universitario', 'Sin Informacion'))
GO

SELECT cc.name
FROM   sys.check_constraints AS cc
WHERE  cc.parent_object_id = OBJECT_ID('dbo.Cliente')
  AND  cc.definition LIKE '%nivel_educacional%';
GO

ALTER TABLE [Cliente] ADD CONSTRAINT FK_Cliente_Region FOREIGN KEY ([region_id]) REFERENCES [Region] ([id_region]);
GO

ALTER TABLE [Cuenta] ADD CONSTRAINT FK_Cuenta_Cliente FOREIGN KEY ([rut_cliente]) REFERENCES [Cliente] ([rut_cliente]);
GO

USE TransactBanco;
GO

BEGIN TRANSACTION;

-- ① Ajustar uso_tarjeta_mensual
IF EXISTS (
    SELECT 1 FROM sys.columns c
    JOIN sys.objects  o ON c.object_id = o.object_id
    WHERE o.name = 'Cuenta' AND c.name = 'uso_tarjeta_mensual' AND c.system_type_id = 104 -- bit
)
BEGIN
    ALTER TABLE dbo.Cuenta
    ALTER COLUMN uso_tarjeta_mensual INT NOT NULL;
END;

-- ② Ampliar saldo_maximo_registrado si fuera menor a 12,2
IF EXISTS (
    SELECT 1 FROM sys.columns c
    JOIN sys.objects  o ON c.object_id = o.object_id
    WHERE o.name = 'Cuenta' AND c.name = 'saldo_maximo_registrado' AND (c.precision < 12 OR c.scale < 2)
)
BEGIN
    ALTER TABLE dbo.Cuenta
    ALTER COLUMN saldo_maximo_registrado DECIMAL(12,2) NOT NULL;
END;

COMMIT;


USE TransactBanco;
GO

BEGIN TRANSACTION;

IF EXISTS (
    SELECT 1 FROM sys.columns c
    JOIN sys.objects  o ON c.object_id = o.object_id
    WHERE o.name = 'Cuenta' AND c.name = 'uso_tarjeta_mensual' AND c.system_type_id = 104 -- bit
)
BEGIN
    ALTER TABLE dbo.Cuenta
    ALTER COLUMN uso_tarjeta_mensual INT NOT NULL;
END;

IF EXISTS (
    SELECT 1 FROM sys.columns c
    JOIN sys.objects  o ON c.object_id = o.object_id
    WHERE o.name = 'Cuenta' AND c.name = 'saldo_maximo_registrado' AND (c.precision < 12 OR c.scale < 2)
)
BEGIN
    ALTER TABLE dbo.Cuenta
    ALTER COLUMN saldo_maximo_registrado DECIMAL(12,0) NOT NULL;
END;

COMMIT;

SELECT * FROM dbo.Cuenta;
SELECT * FROM dbo.Cliente;
SELECT * FROM dbo.Region;

BEGIN TRANSACTION;
DELETE FROM dbo.Cuenta;    
DELETE FROM dbo.Cliente;    
COMMIT;
