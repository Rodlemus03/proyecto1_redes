from flask import Flask, request, jsonify, send_file, Response
from datetime import datetime
import io
import csv
import uuid
import json

app = Flask(__name__)

TASKS = {}
MOCK_ITEMS = [
    {"id": 1, "name": "Widget A", "stock": 25, "price": 12.5},
    {"id": 2, "name": "Widget B", "stock": 5, "price": 19.9},
    {"id": 3, "name": "Widget C", "stock": 0, "price": 7.0},
]

def ok(data=None, **extra):
    payload = {"ok": True, "timestamp": datetime.utcnow().isoformat() + "Z"}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return jsonify(payload)

def fail(msg, code=400, **extra):
    payload = {"ok": False, "error": msg, "timestamp": datetime.utcnow().isoformat() + "Z"}
    payload.update(extra)
    return jsonify(payload), code

def pdf_minimal(text="Reporte MCP"):
    header = b"%PDF-1.4\n"
    objs = []
    obj1 = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    objs.append(obj1)
    obj2 = b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    objs.append(obj2)
    obj3 = b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>\nendobj\n"
    objs.append(obj3)
    stream_content = f"BT /F1 24 Tf 72 770 Td ({text}) Tj ET\n".encode("latin-1")
    obj4 = b"4 0 obj\n<< /Length " + str(len(stream_content)).encode() + b" >>\nstream\n" + stream_content + b"endstream\nendobj\n"
    objs.append(obj4)
    obj5 = b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    objs.append(obj5)
    xref_entries = []
    content = io.BytesIO()
    content.write(header)
    offsets = [0]
    for o in objs:
        offsets.append(content.tell())
        content.write(o)
    xref_start = content.tell()
    xref_count = len(objs) + 1
    xref = ["xref\n0 " + str(xref_count) + "\n"]
    xref.append("{:010} {:05} f \n".format(0, 65535))
    for off in offsets[1:]:
        xref.append("{:010} {:05} n \n".format(off, 0))
    xref_bytes = "".join(xref).encode("ascii")
    content.write(xref_bytes)
    trailer = f"trailer\n<< /Size {xref_count} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode("ascii")
    content.write(trailer)
    content.seek(0)
    return content

@app.get("/api/v1/health")
def health():
    return ok({"service": "mcp-local", "status": "healthy"})

@app.get("/api/v1/info")
def info():
    return ok({
        "name": "MCP Local",
        "version": "1.0.0",
        "capabilities": [
            "auth/audit", "data-api", "reports", "llm-rag", "process-orchestration", "webhooks", "observability"
        ]
    })

@app.get("/api/v1/data/items")
def list_items():
    q = (request.args.get("q") or "").lower().strip()
    data = [x for x in MOCK_ITEMS if q in x["name"].lower()] if q else MOCK_ITEMS
    return ok({"items": data, "count": len(data)})

@app.post("/api/v1/report")
def generate_report():
    body = request.get_json(silent=True) or {}
    rtype = (body.get("type") or "csv").lower()
    rows = MOCK_ITEMS
    if rtype == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
        mem = io.BytesIO(output.getvalue().encode("utf-8"))
        mem.seek(0)
        return send_file(mem, as_attachment=True, download_name=f"reporte_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", mimetype="text/csv")
    elif rtype == "pdf":
        mem = pdf_minimal("Reporte MCP")
        return send_file(mem, as_attachment=True, download_name=f"reporte_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf", mimetype="application/pdf")
    else:
        return fail("Tipo de reporte no soportado. Usa 'csv' o 'pdf'.")

@app.post("/api/v1/process/run")
def run_process():
    body = request.get_json(silent=True) or {}
    name = body.get("name")
    if not name:
        return fail("Falta 'name' del proceso")
    task_id = str(uuid.uuid4())
    TASKS[task_id] = {"status": "queued", "result": None}
    TASKS[task_id]["status"] = "running"
    TASKS[task_id]["result"] = {"name": name, "message": "Proceso ejecutado"}
    TASKS[task_id]["status"] = "done"
    return ok({"task_id": task_id})

@app.get("/api/v1/process/status/<task_id>")
def process_status(task_id):
    task = TASKS.get(task_id)
    if not task:
        return fail("Task no encontrada", 404)
    return ok(task)

@app.post("/api/v1/query")
def llm_query():
    body = request.get_json(silent=True) or {}
    question = (body.get("question") or "").strip()
    if not question:
        return fail("Falta 'question'")
    answer = f"Respuesta a: '{question}'. Integraremos RAG + LLM aquí."
    sources = [{"title": "Manual Interno", "url": None}, {"title": "BD KPIs", "url": None}]
    return ok({"answer": answer, "sources": sources})

OPENAPI = {
    "openapi": "3.0.3",
    "info": {"title": "MCP Local API", "version": "1.0.0", "description": "API del servidor MCP local"},
    "servers": [{"url": "http://localhost:8000"}],
    "paths": {
        "/api/v1/health": {
            "get": {
                "summary": "Revisar estado",
                "responses": {"200": {"description": "OK", "content": {"application/json": {"schema": {"type": "object"}}}}}
            }
        },
        "/api/v1/info": {
            "get": {
                "summary": "Información del servicio",
                "responses": {"200": {"description": "OK", "content": {"application/json": {"schema": {"type": "object"}}}}}
            }
        },
        "/api/v1/data/items": {
            "get": {
                "summary": "Listar items",
                "parameters": [{"name": "q", "in": "query", "required": False, "schema": {"type": "string"}}],
                "responses": {"200": {"description": "OK", "content": {"application/json": {"schema": {
                    "type": "object",
                    "properties": {
                        "ok": {"type": "boolean"},
                        "data": {"type": "object", "properties": {
                            "items": {"type": "array", "items": {"$ref": "#/components/schemas/Item"}},
                            "count": {"type": "integer"}
                        }}
                    }
                }}}}}
            }
        },
        "/api/v1/report": {
            "post": {
                "summary": "Generar reporte",
                "requestBody": {"required": True, "content": {"application/json": {"schema": {
                    "type": "object",
                    "properties": {"type": {"type": "string", "enum": ["csv", "pdf"]}, "params": {"type": "object"}}
                }}}},
                "responses": {"200": {"description": "Archivo generado"}}
            }
        },
        "/api/v1/process/run": {
            "post": {
                "summary": "Ejecutar proceso",
                "requestBody": {"required": True, "content": {"application/json": {"schema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "params": {"type": "object"}},
                    "required": ["name"]
                }}}},
                "responses": {"200": {"description": "Task creada", "content": {"application/json": {"schema": {
                    "type": "object",
                    "properties": {"ok": {"type": "boolean"}, "data": {"type": "object", "properties": {"task_id": {"type": "string"}}}}
                }}}}}
            }
        },
        "/api/v1/process/status/{task_id}": {
            "get": {
                "summary": "Estado de proceso",
                "parameters": [{"name": "task_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                "responses": {"200": {"description": "OK", "content": {"application/json": {"schema": {
                    "type": "object",
                    "properties": {"ok": {"type": "boolean"}, "data": {"$ref": "#/components/schemas/TaskStatus"}}
                }}}}, "404": {"description": "No encontrado"}}
            }
        },
        "/api/v1/query": {
            "post": {
                "summary": "Consulta en lenguaje natural",
                "requestBody": {"required": True, "content": {"application/json": {"schema": {
                    "type": "object",
                    "properties": {"question": {"type": "string"}, "top_k": {"type": "integer"}},
                    "required": ["question"]
                }}}},
                "responses": {"200": {"description": "OK", "content": {"application/json": {"schema": {
                    "type": "object",
                    "properties": {"ok": {"type": "boolean"}, "data": {"$ref": "#/components/schemas/QueryResponse"}}
                }}}}}
            }
        }
    },
    "components": {
        "schemas": {
            "Item": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "name": {"type": "string"}, "stock": {"type": "integer"}, "price": {"type": "number"}}
            },
            "TaskStatus": {
                "type": "object",
                "properties": {"status": {"type": "string"}, "result": {"type": "object"}}
            },
            "QueryResponse": {
                "type": "object",
                "properties": {"answer": {"type": "string"}, "sources": {"type": "array", "items": {"type": "object"}}}
            }
        }
    }
}

@app.get("/openapi.json")
def openapi_json():
    return jsonify(OPENAPI)

@app.get("/docs")
def docs():
    html = """
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8"/>
      <title>MCP Local API Docs</title>
      <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css"/>
      <style>html,body,#swagger{height:100%;margin:0}</style>
    </head>
    <body>
      <div id="swagger"></div>
      <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
      <script>
        window.ui = SwaggerUIBundle({ url: "/openapi.json", dom_id: "#swagger" });
      </script>
    </body>
    </html>
    """
    return Response(html, mimetype="text/html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True, use_reloader=False)
