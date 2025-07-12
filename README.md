# ETL Project - Banco BI Arquitectura y Almacenamiento de Datos

Este proyecto implementa una arquitectura ETL modular para la integración de datos transaccionales en un Data Warehouse (DW). Sigue buenas prácticas de desarrollo, como separación por capas (Extract, Transform, Load), configuración centralizada y logging estructurado.

## 📁 Estructura del Proyecto

etl_project/  
│  
├── etl/  
│ ├── config.py # Configuración centralizada (paths, credenciales, etc.)  
│ ├── pipeline.py # Orquestador principal del flujo ETL  
│ │  
│ ├── extract/  
│ │ └── excel_reader.py # Módulos para leer archivos fuente (XLSX, CSV, etc.)  
│ │  
│ ├── transform/  
│ │ ├── data_cleaner.py # Limpieza y estandarización de datos brutos  
│ │ ├── dim_builder.py # Construcción de dimensiones a partir de datos transaccionales  
│ │ └── fact_builder.py # Generación de la tabla de hechos con claves sustitutas y métricas  
│ │  
│ ├── load/  
│ │ ├── cleanup.py # Eliminación previa de datos en tablas destino (truncado/reset)  
│ │ ├── dim_loaders.py # Inserción de dimensiones al Data Warehouse  
│ │ ├── load_to_db.py  # Carga de datos hacia el entorno operacional (SQL Server)  
│ │ ├── load_to_dw.py # Carga final al DW con surrogate keys y dimensiones  
│ │ └── load_to_staging.py  # Carga en zona de staging para transformaciones intermedias  
│ │  
│ └── utils/  
│ └── logger.py # Configuración de logger personalizado  
│  
├── tests/ # Pruebas unitarias por etapa  
│ ├── test_extract.py  
│ └── test_transform.py  
│  
├── run_etl.py # Script de entrada para ejecución manual  
├── requirements.txt # Dependencias del proyecto  
└── README.md  


## 🚀 Instrucciones de instalación

1. Clona el repositorio:

```bash
git clone https://github.com/Stivaly/banco-bi.git
cd etl_project
```

2. Crea un entorno virtual:
```bash
python -m venv venv
source venv/bin/activate    # En Linux/macOS
venv\Scripts\activate.bat   # En Windows
```
3. Instala las dependencias:
```bash
pip install -r requirements.txt
```

## 🧩 Ejecución del ETL

```bash
python run_etl.py
```

## ✅ Buenas prácticas aplicadas

- Lógica desacoplada (extract, transform, load en módulos separados).

- Configuración centralizada (config.py).

- Logging estructurado (logger.py).

- Sin hardcodeo de rutas ni credenciales.

- Test unitarios para cada módulo.

- Tipado estático (type hints).

- Diseño extensible y reutilizable.

## 🏁 Licencia

- Apache License Version 2.0, January 2004
