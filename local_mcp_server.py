from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime
from typing import Dict, Any, List
import pandas as pd
import os, io, csv, uuid, json, glob, base64, pathlib, re


BASE_DIR = pathlib.Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"
FILES_DIR = BASE_DIR / "files"     
DOCS_DIR = DATA_DIR / "docs"       
for d in [DATA_DIR, FILES_DIR, DOCS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

SALES_CSV = DATA_DIR / "sales.csv"
INV_CSV   = DATA_DIR / "inventory.csv"

if not SALES_CSV.exists():
    pd.DataFrame([
        {"month":"Agosto","product":"Laptop Pro","units":15,"unit_price":1200.0},
        {"month":"Agosto","product":"Mouse X","units":120,"unit_price":20.0},
        {"month":"Agosto","product":"Teclado Mecánico","units":75,"unit_price":50.0},
        {"month":"Agosto","product":"Monitor 27\"", "units":20,"unit_price":300.0},
        {"month":"Septiembre","product":"Laptop Pro","units":10,"unit_price":1200.0},
        {"month":"Septiembre","product":"Mouse X","units":140,"unit_price":20.0},
    ]).to_csv(SALES_CSV, index=False, encoding="utf-8")
if not INV_CSV.exists():
    pd.DataFrame([
        {"product":"Laptop Pro","stock":8,"min_required":10},
        {"product":"Mouse X","stock":500,"min_required":200},
        {"product":"Teclado Mecánico","stock":50,"min_required":30},
        {"product":"Monitor 27\"", "stock":5,"min_required":15},
    ]).to_csv(INV_CSV, index=False, encoding="utf-8")
demo_doc = DOCS_DIR / "politica_calidad.txt"
if not demo_doc.exists():
    demo_doc.write_text("Nuestra política de calidad exige mantener inventario de seguridad y lead time de 7 días en línea de monitores.", encoding="utf-8")


def rpc_ok(req_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}

def rpc_err(req_id: str, message: str, code: int = -32000) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

def text_piece(text: str) -> Dict[str, str]:
    return {"type":"text","text":text}

def tool_result(text: str, is_error: bool = False) -> Dict[str, Any]:
    return {"content":[text_piece(text)], "isError": is_error}

def load_sales() -> pd.DataFrame:
    return pd.read_csv(SALES_CSV, encoding="utf-8")

def load_inventory() -> pd.DataFrame:
    return pd.read_csv(INV_CSV, encoding="utf-8")

def to_currency(x: float) -> str:
    return f"${x:,.2f}"


def llm_answer(query: str, context: str) -> str:
 
    bullets = re.findall(r"\b\w+\b", query.lower())
    hints = ", ".join(sorted(set(bullets)))[:120]
    return f"[LLM] Respuesta a: '{query}'. Contexto usado ({len(context)} chars). Palabras clave: {hints or 'n/a'}"

def build_context(sales_df: pd.DataFrame, inv_df: pd.DataFrame, docs_text: str) -> str:
    revenue = (sales_df["units"]*sales_df["unit_price"]).sum()
    top_prod = sales_df.assign(revenue=sales_df["units"]*sales_df["unit_price"]) \
                       .sort_values("revenue", ascending=False).head(1)
    top_line = ""
    if not top_prod.empty:
        r = top_prod.iloc[0]
        top_line = f"TOP: {r['product']} ({to_currency(r['revenue'])})"
    critical = inv_df[inv_df["stock"] < inv_df["min_required"]]
    crit_names = ", ".join(critical["product"].tolist()) if not critical.empty else "ninguno"
    docs_excerpt = (docs_text[:300] + "...") if len(docs_text) > 300 else docs_text
    return (
        f"KPI ventas totales: {to_currency(revenue)} | {top_line}\n"
        f"Inventario crítico: {crit_names}\n"
        f"Docs: {docs_excerpt}"
    )

def read_all_docs() -> str:
    chunks = []
    for path in glob.glob(str(DOCS_DIR / "*.txt")):
        try:
            chunks.append(pathlib.Path(path).read_text(encoding="utf-8"))
        except:
            pass
    return "\n\n".join(chunks)


def minimal_pdf(title: str, lines: List[str]) -> bytes:
    body = f"BT /F1 16 Tf 72 770 Td ({title}) Tj ET\n"
    y = 740
    for ln in lines[:40]:
        safe = ln.replace("(", "[").replace(")", "]")
        body += f"BT /F1 10 Tf 72 {y} Td ({safe}) Tj ET\n"
        y -= 14
        if y < 50: break
    stream = body.encode("latin-1","ignore")
    objs = []
    objs.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objs.append(b"2 0 obj<< /Type /Pages /Count 1 /Kids [3 0 R] >>endobj\n")
    objs.append(b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>endobj\n")
    objs.append(b"4 0 obj<< /Length " + str(len(stream)).encode() + b" >>stream\n" + stream + b"\nendstream endobj\n")
    objs.append(b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n")
    output = io.BytesIO()
    output.write(b"%PDF-1.4\n")
    offsets=[0]
    for o in objs:
        offsets.append(output.tell())
        output.write(o)
    xref_start = output.tell()
    output.write(f"xref\n0 {len(objs)+1}\n".encode())
    output.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        output.write(f"{off:010} 00000 n \n".encode())
    output.write(b"trailer<< /Size " + str(len(objs)+1).encode() + b" /Root 1 0 R >>\n")
    output.write(f"startxref\n{xref_start}\n%%EOF".encode())
    output.seek(0)
    return output.read()

def save_file(name: str, data: bytes) -> str:
    p = FILES_DIR / name
    p.write_bytes(data)
    return str(p.name)


def tool_sales_summary(args: Dict[str, Any]) -> Dict[str, Any]:
    df = load_sales()
    month = args.get("month")
    if month:
        df = df[df["month"].str.lower()==str(month).lower()]
    df = df.assign(revenue=df["units"]*df["unit_price"])
    total = to_currency(df["revenue"].sum())
    by_prod = df.groupby("product")["revenue"].sum().sort_values(ascending=False)
    lines = [f"RESUMEN DE VENTAS ({month or 'todos'})",
             f"Ingreso total: {total}",
             "Por producto:"]
    for prod, rev in by_prod.items():
        lines.append(f" - {prod}: {to_currency(rev)}")
    return tool_result("\n".join(lines))

def tool_sales_top(args: Dict[str, Any]) -> Dict[str, Any]:
    df = load_sales().assign(revenue=lambda x: x["units"]*x["unit_price"])
    metric = (args.get("by") or "revenue").lower()
    n = int(args.get("n", 5))
    if metric not in ("revenue","units"): metric="revenue"
    key = "revenue" if metric=="revenue" else "units"
    agg = df.groupby("product")[key].sum().sort_values(ascending=False).head(n)
    lines=[f"TOP {n} productos por {metric}:"]
    for prod, val in agg.items():
        lines.append(f" - {prod}: {to_currency(val) if metric=='revenue' else int(val)}")
    return tool_result("\n".join(lines))

def tool_inventory_status(args: Dict[str, Any]) -> Dict[str, Any]:
    inv = load_inventory()
    lines = ["ESTADO DE INVENTARIO:"]
    for _, r in inv.iterrows():
        status = "CRÍTICO" if r["stock"] < r["min_required"] else "OK"
        lines.append(f" - {r['product']}: {int(r['stock'])} (mín {int(r['min_required'])}) → {status}")
    return tool_result("\n".join(lines))

def tool_inventory_reorder(args: Dict[str, Any]) -> Dict[str, Any]:
    inv = load_inventory()
    lead_days = int(args.get("lead_time_days", 7))
    safety = float(args.get("safety_factor", 1.2))
    recs=[]
    for _, r in inv.iterrows():
        if r["stock"] < r["min_required"]:
            qty = int(max(0, r["min_required"]*safety - r["stock"]))
            recs.append(f" - {r['product']}: pedir {qty} (lead {lead_days} días)")
    text = "SUGERENCIAS DE REABASTECIMIENTO:\n" + ("\n".join(recs) if recs else " Todo en orden.")
    return tool_result(text)

def tool_report_generate(args: Dict[str, Any]) -> Dict[str, Any]:
    rtype = (args.get("type") or "general").lower()  
    fmt   = (args.get("format") or "csv").lower()    
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if rtype == "ventas":
        df = load_sales().assign(revenue=lambda x: x["units"]*x["unit_price"])
        if fmt=="csv":
            name=f"reporte_ventas_{ts}.csv"
            df.to_csv(FILES_DIR/name, index=False, encoding="utf-8")
            link=f"/files/{name}"
            return tool_result(f"Reporte de ventas generado: {link}")
        else:
            lines = ["REPORTE DE VENTAS"] + [f"{r.product}: {int(r.units)} u, {to_currency(r.unit_price)} c/u" for r in df.itertuples()]
            pdf = minimal_pdf("Reporte de Ventas", lines)
            name=f"reporte_ventas_{ts}.pdf"
            save_file(name, pdf)
            link=f"/files/{name}"
            return tool_result(f"Reporte PDF de ventas: {link}")
    elif rtype == "inventario":
        df = load_inventory()
        if fmt=="csv":
            name=f"reporte_inventario_{ts}.csv"
            df.to_csv(FILES_DIR/name, index=False, encoding="utf-8")
            return tool_result(f"Reporte de inventario generado: /files/{name}")
        else:
            lines=["REPORTE INVENTARIO"] + [f"{r.product}: stock {int(r.stock)} / min {int(r.min_required)}" for r in df.itertuples()]
            pdf=minimal_pdf("Reporte de Inventario", lines)
            name=f"reporte_inventario_{ts}.pdf"
            save_file(name, pdf)
            return tool_result(f"Reporte PDF de inventario: /files/{name}")
    else:
        lines = ["REPORTE GENERAL",
                 tool_sales_summary({})["content"][0]["text"],
                 "",
                 tool_inventory_status({})["content"][0]["text"]]
        pdf=minimal_pdf("Reporte General", lines)
        name=f"reporte_general_{ts}.pdf"
        save_file(name, pdf)
        return tool_result(f"Reporte general PDF: /files/{name}")

def tool_docs_search(args: Dict[str, Any]) -> Dict[str, Any]:
    q = (args.get("q") or "").strip().lower()
    if not q: return tool_result("Proporcione 'q' (query).", True)
    found=[]
    for path in glob.glob(str(DOCS_DIR/"*.txt")):
        txt = pathlib.Path(path).read_text(encoding="utf-8", errors="ignore").lower()
        if q in txt:
            found.append(os.path.basename(path))
    text = "Coincidencias: " + (", ".join(found) if found else "ninguna")
    return tool_result(text)

def tool_ask_llm(args: Dict[str, Any]) -> Dict[str, Any]:
    q = (args.get("query") or "").strip()
    if not q: return tool_result("Falta 'query'", True)
    sales = load_sales()
    inv   = load_inventory()
    docs  = read_all_docs()
    ctx   = build_context(sales, inv, docs)
    answer = llm_answer(q, ctx)
    return tool_result(answer)

def tool_ingest_csv(args: Dict[str, Any]) -> Dict[str, Any]:
    kind = (args.get("kind") or "").lower()
    b64  = args.get("csv_base64")
    if kind not in ("sales","inventory"): return tool_result("kind debe ser 'sales' o 'inventory'", True)
    if not b64: return tool_result("Falta csv_base64", True)
    try:
        raw = base64.b64decode(b64)
        df = pd.read_csv(io.BytesIO(raw))
        if kind=="sales":
            for col in ["month","product","units","unit_price"]:
                if col not in df.columns: return tool_result(f"CSV ventas sin columna {col}", True)
            df.to_csv(SALES_CSV, index=False, encoding="utf-8")
        else:
            for col in ["product","stock","min_required"]:
                if col not in df.columns: return tool_result(f"CSV inventario sin columna {col}", True)
            df.to_csv(INV_CSV, index=False, encoding="utf-8")
        return tool_result(f"Datos '{kind}' actualizados ({len(df)} filas).")
    except Exception as e:
        return tool_result(f"Error ingestando CSV: {e}", True)

TOOLS: Dict[str, Dict[str, Any]] = {
    "sales.summary":               {"description": "Resumen de ventas (opcional: month)", "func": tool_sales_summary,
                                    "inputSchema":{"type":"object","properties":{"month":{"type":"string"}}}},
    "sales.top":                   {"description": "Top N productos por revenue|units", "func": tool_sales_top,
                                    "inputSchema":{"type":"object","properties":{"n":{"type":"integer"}, "by":{"type":"string"}}}},
    "inventory.status":            {"description": "Estado actual del inventario (críticos/OK)", "func": tool_inventory_status,
                                    "inputSchema":{"type":"object","properties":{}}},
    "inventory.reorder_suggestions":{"description":"Sugerencias de reabastecimiento", "func": tool_inventory_reorder,
                                    "inputSchema":{"type":"object","properties":{"lead_time_days":{"type":"integer"},"safety_factor":{"type":"number"}}}},
    "report.generate":             {"description": "Genera reportes CSV/PDF (ventas|inventario|general)", "func": tool_report_generate,
                                    "inputSchema":{"type":"object","properties":{"type":{"type":"string"},"format":{"type":"string"}}}},
    "docs.search":                 {"description": "Búsqueda simple en documentos internos (.txt)", "func": tool_docs_search,
                                    "inputSchema":{"type":"object","properties":{"q":{"type":"string"}},"required":["q"]}},
    "llm.ask":                     {"description": "Pregunta en lenguaje natural usando contexto de ventas+inventario+docs", "func": tool_ask_llm,
                                    "inputSchema":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}},
    "admin.ingest_csv":            {"description": "Ingesta de CSV (sales|inventory) vía base64", "func": tool_ingest_csv,
                                    "inputSchema":{"type":"object","properties":{"kind":{"type":"string"},"csv_base64":{"type":"string"}},"required":["kind","csv_base64"]}},
}


app = Flask(__name__)
CORS(app)

@app.route("/")
def root():
    return jsonify({
        "service":"Enterprise MCP Server (ventas+inventario+docs)",
        "status":"ok",
        "version":"2.0.0",
        "timestamp": datetime.now().isoformat(),
        "endpoints":["/health","/mcp/tools/list","/mcp/tools/call","/files/<name>"]
    })

@app.route("/health", methods=["GET"])
def health():
    s = load_sales()
    i = load_inventory()
    return jsonify({
        "status":"healthy",
        "rows":{"sales":int(len(s)), "inventory":int(len(i))},
        "time": datetime.now().isoformat()
    })

@app.route("/mcp/tools/list", methods=["GET"])
def list_tools():
    tools = [{"name":k,"description":v["description"],"inputSchema":v.get("inputSchema",{"type":"object"})} for k,v in TOOLS.items()]
    return jsonify({"tools": tools})

@app.route("/mcp/tools/call", methods=["POST"])
def call_tool():
    data = request.get_json(force=True) or {}
    name = data.get("name")
    args = data.get("arguments", {}) or {}
    req_id = data.get("id", str(uuid.uuid4()))
    if name not in TOOLS:
        return jsonify(rpc_err(req_id, f"Tool '{name}' no encontrado")), 400
    try:
        result = TOOLS[name]["func"](args)
        return jsonify(rpc_ok(req_id, result)), 200
    except Exception as e:
        return jsonify(rpc_err(req_id, f"Error ejecutando '{name}': {e}")), 500

@app.route("/files/<path:fname>", methods=["GET"])
def files_serve(fname: str):
    # descarga de archivos generados
    return send_from_directory(FILES_DIR, fname, as_attachment=True)

if __name__=="__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
