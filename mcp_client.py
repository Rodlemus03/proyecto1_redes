import aiohttp, asyncio, base64, json, re, pathlib
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

# BASE_URL = "http://127.0.0.1:5000"
BASE_URL = "https://proyecto1-redes.onrender.com"

console = Console()


async def http_get(path: str):
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{BASE_URL}{path}") as r:
            return await r.json()

async def http_post(path: str, payload: dict):
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{BASE_URL}{path}", json=payload) as r:
            data = await r.json()
            return r.status, data

async def call_tool(name: str, arguments: dict):
    payload = {"id": f"req-{datetime.now().timestamp()}", "name": name, "arguments": arguments}
    status, data = await http_post("/mcp/tools/call", payload)
    if "result" in data:
        for item in data["result"]["content"]:
            console.print(Panel(item.get("text","(sin texto)"), title=f"{name} [{status}]"))
    else:
        console.print(Panel(str(data), title=f"Error [{status}]", style="red"))


async def ingest_csv(kind: str, path: str):
    p = pathlib.Path(path).expanduser()
    if not p.exists():
        console.print(f"[red]Archivo no encontrado: {p}[/red]"); return
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    await call_tool("admin.ingest_csv", {"kind": kind, "csv_base64": b64})


MONTHS_ES = {
    "enero":"Enero","febrero":"Febrero","marzo":"Marzo","abril":"Abril","mayo":"Mayo","junio":"Junio",
    "julio":"Julio","agosto":"Agosto","septiembre":"Septiembre","setiembre":"Septiembre",
    "octubre":"Octubre","noviembre":"Noviembre","diciembre":"Diciembre"
}

def extract_month(text: str):
    t = text.lower()
    for k,v in MONTHS_ES.items():
        if k in t:
            return v
    return None

def extract_top(text: str):
    # “top 3”, “top3”, “los 5 más”, etc.
    m = re.search(r"top\s*([0-9]+)", text, re.I) or re.search(r"los\s+([0-9]+)\s+m[aá]s", text, re.I)
    return int(m.group(1)) if m else None

def prefers_units(text: str):
    return bool(re.search(r"\b(unidades|u\.?|por unidades)\b", text, re.I))

def prefers_revenue(text: str):
    return bool(re.search(r"\b(ventas|ingresos|revenue|facturaci[oó]n)\b", text, re.I))

def wants_pdf(text: str):
    return bool(re.search(r"\bpdf\b", text, re.I))

def wants_csv(text: str):
    return bool(re.search(r"\bcsv\b", text, re.I))

def is_inventory_query(text: str):
    return bool(re.search(r"\b(inventario|stock|existencias|almac[eé]n)\b", text, re.I))

def is_sales_query(text: str):
    return bool(re.search(r"\b(venta|ventas|facturaci[oó]n|ingresos)\b", text, re.I))

def is_report_request(text: str):
    return bool(re.search(r"\b(reporte|informe|genera|generar|exporta|exportar)\b", text, re.I))

def is_docs_search(text: str):
    return bool(re.search(r"\b(doc|documento|pol[ií]tica|manual|procedimiento|buscar en doc)\b", text, re.I))

def extract_docs_query(text: str):
    m = re.search(r"[\"“](.+?)[\"”]", text)
    if m: return m.group(1)
    m = re.search(r"(sobre|de|acerca de)\s+(.+)$", text, re.I)
    if m: return m.group(2).strip()
    words = [w for w in re.findall(r"\w{5,}", text)]
    return " ".join(words[:6]) if words else None

def route_nl(text: str):
 
    t = text.strip()

    if is_report_request(t):
        fmt = "pdf" if wants_pdf(t) else ("csv" if wants_csv(t) else "pdf")
        if is_inventory_query(t):
            return ("report.generate", {"type":"inventario", "format": fmt})
        if is_sales_query(t):
            return ("report.generate", {"type":"ventas", "format": fmt})
        return ("report.generate", {"type":"general", "format": fmt})

    if is_sales_query(t) and re.search(r"\b(top|los\s+\d+\s+m[aá]s)\b", t, re.I):
        n = extract_top(t) or 5
        by = "units" if prefers_units(t) and not prefers_revenue(t) else "revenue"
        return ("sales.top", {"n": n, "by": by})

    if is_sales_query(t) or re.search(r"\bresumen\b", t, re.I):
        month = extract_month(t)
        args = {"month": month} if month else {}
        return ("sales.summary", args)

    if is_inventory_query(t) and re.search(r"\b(reabaste|reorden|reponer|sugerencia)\b", t, re.I):
        m_lead = re.search(r"lead\s*(?:time)?\s*(\d+)", t, re.I)
        m_sf   = re.search(r"(safety\s*factor|factor\s*seguridad)\s*([0-9]+(\.[0-9]+)?)", t, re.I)
        args={}
        if m_lead: args["lead_time_days"] = int(m_lead.group(1))
        if m_sf:   args["safety_factor"]  = float(m_sf.group(2))
        return ("inventory.reorder_suggestions", args or {})

    if is_inventory_query(t):
        return ("inventory.status", {})

    if is_docs_search(t):
        q = extract_docs_query(t)
        if q: return ("docs.search", {"q": q})

    return None  

HELP = (
"[bold]MCP Empresa — Modo híbrido[/bold]\n"
"[green]Puedes escribir preguntas libres[/green] o usar comandos.\n\n"
"[bold]Ejemplos NL:[/bold]\n"
"• ¿Qué tal las ventas de agosto?\n"
"• Top 3 productos por unidades\n"
"• Genera un PDF del inventario\n"
"• Exporta a CSV un reporte de ventas\n"
"• Búscame en los documentos “inventario de seguridad”\n"
"• ¿Necesito reabastecer? factor seguridad 1.3 lead 10\n"
"• Haz un resumen ejecutivo de ventas e inventario\n\n"
"[bold]Comandos:[/bold]\n"
"/tools, /health, /ask \"pregunta\", /sales month=Agosto, /top n=3 by=units,\n"
"/inv, /reorder lead_time_days=10 safety_factor=1.3,\n"
"/report type=ventas format=pdf, /docs q=\"texto\",\n"
"/ingest kind=sales path=./mis_ventas.csv, /quit\n"
)

def parse_cmd_args(argstr: str) -> dict:
    argstr = argstr.strip()
    if not argstr: return {}
    try:
        return json.loads(argstr)
    except:
        out={}
        parts = [p.strip() for p in argstr.split() if p.strip()]
        for p in parts:
            if "=" in p:
                k,v = p.split("=",1)
                if v.isdigit(): v=int(v)
                else:
                    try: v=float(v)
                    except: v=v.strip('"\'')
                out[k]=v
        return out

async def list_tools_ui():
    data = await http_get("/mcp/tools/list")
    names = "\n".join(f"• {t['name']}: {t['description']}" for t in data["tools"])
    console.print(Panel(names, title="Herramientas", border_style="cyan"))

async def main():
    console.print(Panel(HELP, title="Ayuda", border_style="green"))
    while True:
        msg = Prompt.ask("[bold cyan]>[/]").strip()
        if not msg: continue
        if msg.lower() in ("/quit","salir","exit"): break

        if msg == "/tools":
            await list_tools_ui(); continue
        if msg == "/health":
            console.print(Panel(json.dumps(await http_get("/health"), indent=2, ensure_ascii=False), title="health")); continue
        if msg.startswith("/ask"):
            q = msg[len("/ask"):].strip().strip('"').strip("'")
            if not q: console.print("[yellow]Uso: /ask \"pregunta\"[/yellow]"); continue
            await call_tool("llm.ask", {"query": q}); continue
        if msg.startswith("/sales"):
            args = parse_cmd_args(msg[len("/sales"):]); await call_tool("sales.summary", args); continue
        if msg.startswith("/top"):
            args = parse_cmd_args(msg[len("/top"):]); await call_tool("sales.top", args); continue
        if msg == "/inv":
            await call_tool("inventory.status", {}); continue
        if msg.startswith("/reorder"):
            args = parse_cmd_args(msg[len("/reorder"):]); await call_tool("inventory.reorder_suggestions", args); continue
        if msg.startswith("/report"):
            args = parse_cmd_args(msg[len("/report"):]); await call_tool("report.generate", args); continue
        if msg.startswith("/docs"):
            args = parse_cmd_args(msg[len("/docs"):])
            if not args.get("q"): console.print("[yellow]Uso: /docs q=\"texto\"[/yellow]"); continue
            await call_tool("docs.search", args); continue
        if msg.startswith("/ingest"):
            args = parse_cmd_args(msg[len("/ingest"):])
            kind, path = args.get("kind"), args.get("path")
            if not kind or not path:
                console.print("[yellow]Uso: /ingest kind=sales|inventory path=./archivo.csv[/yellow]"); continue
            await ingest_csv(kind, path); continue

        routed = route_nl(msg)
        if routed:
            name, arguments = routed
            await call_tool(name, arguments)
            continue

        await call_tool("llm.ask", {"query": msg})

if __name__=="__main__":
    asyncio.run(main())
