# MCP Local API

Servidor Flask minimal para demos de **MCP** con endpoints de salud, catálogo de datos, generación de reportes (CSV/PDF), ejecución de procesos simulados, consultas LLM mock y documentación OpenAPI/Swagger.

---

## Requisitos

- **Python 3.9+** (recomendado 3.10/3.11)  
- `pip` y (opcional) `virtualenv`  
- Puerto **8000** libre en tu máquina  

> No requiere base de datos. Todo se maneja en memoria.

---

## Instalación

```bash
# 1) Crea y activa un entorno virtual OPCIONAL
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

# 2) Instala dependencias
pip install --upgrade pip
pip install flask
```

## Ejecución

```bash
python server.py
```

- El servidor arranca en: `http://0.0.0.0:8000`  
- Documentación interactiva (Swagger UI): `http://localhost:8000/docs`  
- Esquema OpenAPI JSON: `http://localhost:8000/openapi.json`  

---

## Endpoints disponibles

| Método | Ruta                                   | Descripción                                 |
|-------:|----------------------------------------|---------------------------------------------|
| GET    | `/api/v1/health`                       | Estado del servicio                          |
| GET    | `/api/v1/info`                         | Info y capacidades                           |
| GET    | `/api/v1/data/items?q=<str>`           | Listar items (filtro opcional por `q`)       |
| POST   | `/api/v1/report`                       | Generar **CSV** o **PDF** (`type: csv|pdf`)  |
| POST   | `/api/v1/process/run`                  | Ejecutar proceso simulado                    |
| GET    | `/api/v1/process/status/<task_id>`     | Consultar estado de proceso                  |
| POST   | `/api/v1/query`                        | Consulta LLM mock                            |
| GET    | `/openapi.json`                        | OpenAPI (3.0.3)                              |
| GET    | `/docs`                                | Swagger UI                                   |

---

## Ejemplos con `curl`

### Salud
```bash
curl -s http://localhost:8000/api/v1/health | jq
```

### Info
```bash
curl -s http://localhost:8000/api/v1/info | jq
```

### Listar items
```bash
curl -s "http://localhost:8000/api/v1/data/items" | jq
curl -s "http://localhost:8000/api/v1/data/items?q=widget" | jq
```

### Reporte CSV
```bash
curl -X POST http://localhost:8000/api/v1/report \
  -H "Content-Type: application/json" \
  -d '{"type":"csv"}' \
  -o reporte.csv
```

### Reporte PDF
```bash
curl -X POST http://localhost:8000/api/v1/report \
  -H "Content-Type: application/json" \
  -d '{"type":"pdf"}' \
  -o reporte.pdf
```

### Ejecutar proceso y consultar status
```bash
# Run
TASK_ID=$(curl -s -X POST http://localhost:8000/api/v1/process/run \
  -H "Content-Type: application/json" \
  -d '{"name":"proceso_demo"}' | jq -r '.data.task_id')

# Status
curl -s "http://localhost:8000/api/v1/process/status/$TASK_ID" | jq
```

### Consulta LLM mock
```bash
curl -s -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question":"¿Qué inventario tengo hoy?"}' | jq
```

---

## Importar en Postman

1. Levanta el servidor y abre `http://localhost:8000/openapi.json`.  
2. Guarda el contenido como archivo **`MCP Local API.postman_collection.json`**.  
3. En Postman: `Import > File > MCP Local API.postman_collection.json`.  
4. Tendrás todos los endpoints listos para probar.  

---
