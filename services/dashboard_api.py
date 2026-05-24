"""
dashboard_api.py — Real-time dashboard API.
Reads state files directly from disk. No GitHub API calls. No rate limits.
Serves the dashboard HTML at / and all data at /api/*.
Auth: DASHBOARD_TOKEN checked on every request (from .env).
"""
import os, json, glob, time
from pathlib import Path
from datetime import datetime, timezone
from fastapi import FastAPI, WebSocket, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn, asyncio

B = Path(os.path.expanduser("~/btc-agents"))
app = FastAPI(docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def load_env():
    env = {}
    with open(B / ".env") as f:
        for line in f:
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1); env[k.strip()] = v.strip()
    return env

ENV = load_env()
DASHBOARD_TOKEN = ENV.get("DASHBOARD_TOKEN", "")

def load(path, default=None):
    try:
        with open(B / path) as f: return json.load(f)
    except: return default

def check_token(request: Request):
    token = request.query_params.get("token") or request.headers.get("X-Dashboard-Token")
    if DASHBOARD_TOKEN and token != DASHBOARD_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")
    return True

# ── Serve dashboard HTML ───────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def dashboard_root(request: Request):
    check_token(request)
    html_path = B / "dashboard" / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text())
    return HTMLResponse("<h1>Dashboard not found. Run the setup prompt.</h1>", status_code=503)

# ── API Endpoints ──────────────────────────────────────────────────
@app.get("/api/status")
async def api_status(request: Request):
    check_token(request)
    sys_state = load("state/system_state.json", {})
    directive = load("state/orchestrator-directive.json", {})
    portfolio = load("state/portfolio.json", {})
    anomaly = load("state/anomaly_state.json", {})
    collection = load("data/meta/collection_status.json", {})
    ws_prices = load("data/market/ws_prices.json", {})
    btc_price = ws_prices.get("BTCUSDT", {}).get("price", 0)

    return {
        "cold_start_day": sys_state.get("cold_start_day", 0),
        "is_cold_start": sys_state.get("is_cold_start", True),
        "demo_mode": portfolio.get("demo_mode", True),
        "circuit_breaker_tripped": portfolio.get("circuit_breaker_tripped", False),
        "signal_watcher_paused": directive.get("signal_watcher_paused", False),
        "dca_enabled": directive.get("dca_enabled", True),
        "anomaly_active": bool(anomaly.get("current_anomalies")),
        "btc_price_usd": btc_price,
        "collection_health": collection.get("collectors", {}),
        "last_updated": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/portfolio")
async def api_portfolio(request: Request):
    check_token(request)
    return load("state/portfolio.json", {})

@app.get("/api/pipeline")
async def api_pipeline(request: Request):
    check_token(request)
    pipe = load("state/pipeline_state.json", {})
    syslog = load("state/system-log.json", {"entries": []})
    entries = syslog.get("entries", []) if isinstance(syslog, dict) else []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_runs = [e for e in entries if e.get("timestamp", "").startswith(today)]
    return {"pipeline": pipe, "today_runs": today_runs[-30:]}

@app.get("/api/strategies")
async def api_strategies(request: Request):
    check_token(request)
    strats = load("state/strategies.json", {})
    strategies = strats.get("strategies", [])
    by_status = {}
    for s in strategies:
        st = s.get("status", "unknown")
        by_status[st] = by_status.get(st, 0) + 1
    return {"strategies": strategies, "by_status": by_status, "total": len(strategies)}

@app.get("/api/research")
async def api_research(request: Request):
    check_token(request)
    research = load("state/research.json", {})
    hypotheses = load("data/proposed_hypotheses.json", {})
    return {"research": research, "today_hypotheses": hypotheses}

@app.get("/api/triggers")
async def api_triggers(request: Request):
    check_token(request)
    queue = load("signals/trigger_queue.json", {"queue": []})
    live = load("signals/live_triggers.json", {"triggers": []})
    return {
        "queue": queue.get("queue", [])[-20:],
        "live_count": len(live.get("triggers", []))
    }

@app.get("/api/debates")
async def api_debates(request: Request):
    check_token(request)
    debates_dir = B / "data/debates"
    debates = []
    if debates_dir.exists():
        for f in sorted(debates_dir.glob("*.json"), reverse=True)[:10]:
            try:
                data = json.loads(f.read_text())
                debates.append({"id": f.stem, **data})
            except: pass
    return {"debates": debates}

@app.get("/api/debates/{chain_id}")
async def api_debate_detail(chain_id: str, request: Request):
    check_token(request)
    path = B / "data/debates" / f"{chain_id}.json"
    if not path.exists():
        raise HTTPException(404, "Debate not found")
    return json.loads(path.read_text())

@app.get("/api/analysts")
async def api_analysts(request: Request):
    check_token(request)
    reports = {}
    for name in ["technical_analyst","derivatives_analyst","onchain_macro_analyst","sentiment_news_analyst"]:
        report = load(f"data/analyst_reports/{name}.json", {})
        done = (B / f"data/analyst_reports/{name}.done").exists()
        reports[name] = {"report": report, "done": done}
    return reports

@app.get("/api/costs")
async def api_costs(request: Request):
    check_token(request)
    syslog = load("state/system-log.json", {"entries": []})
    entries = syslog.get("entries", []) if isinstance(syslog, dict) else []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_runs = [e for e in entries if e.get("timestamp", "").startswith(today)]

    cost_map = {
        "orchestrator": 0.09, "bull-researcher": 0.13, "bear-researcher": 0.12,
        "trader-entry": 0.06, "journal-agent": 0.15,
    }
    haiku_agents = ["technical-analyst","derivatives-analyst","onchain-macro-analyst",
                    "sentiment-news-analyst","hypothesis-generator","synthesis",
                    "strategy-tester","risk-manager","trader-management","reporter"]

    total_today = 0.0
    breakdown = {}
    for run in today_runs:
        agent = run.get("agent","")
        cost = cost_map.get(agent, 0.03 if agent in haiku_agents else 0.0)
        breakdown[agent] = breakdown.get(agent, 0) + cost
        total_today += cost

    return {"today": round(total_today, 3), "breakdown": breakdown, "mtd": round(total_today * 15, 2)}

@app.get("/api/risk-stats")
async def api_risk_stats(request: Request):
    check_token(request)
    queue = load("signals/trigger_queue.json", {"queue": []})
    all_triggers = queue.get("queue", [])
    evaluated = [t for t in all_triggers if t.get("verdict")]
    approved = [t for t in evaluated if t.get("verdict") == "APPROVED"]
    rejected_risk = [t for t in evaluated if "risk" in t.get("rejection_reason","").lower()]
    rejected_thesis = [t for t in evaluated if "thesis" in t.get("rejection_reason","").lower()]
    return {
        "total_evaluated": len(evaluated),
        "approved": len(approved),
        "rejected_risk": len(rejected_risk),
        "rejected_thesis": len(rejected_thesis),
        "approval_rate": round(len(approved)/max(len(evaluated),1)*100, 1),
        "top_rejection_reason": "regime mismatch" if rejected_thesis else "none"
    }

@app.get("/api/lessons")
async def api_lessons(request: Request):
    check_token(request)
    lessons = load("state/lessons.json", {})
    all_lessons = lessons.get("lessons", []) if isinstance(lessons, dict) else []
    return {"lessons": all_lessons[-10:], "total": len(all_lessons)}

@app.get("/api/agents/memory/{agent_name}")
async def api_agent_memory(agent_name: str, request: Request):
    check_token(request)
    memory = {}
    for fname in ["short_term.json","medium_term.json","long_term.json"]:
        data = load(f"hermes/{agent_name}/memory/{fname}", {})
        if data: memory[fname.replace(".json","")] = data
    reflections_path = B / f"hermes/{agent_name}/memory/reflections.jsonl"
    reflections = []
    if reflections_path.exists():
        for line in reflections_path.read_text().strip().split("\n")[-5:]:
            try: reflections.append(json.loads(line))
            except: pass
    memory["recent_reflections"] = reflections
    return memory

# ── WebSocket: live BTC price ──────────────────────────────────────
@app.websocket("/ws/prices")
async def ws_prices(websocket: WebSocket):
    token = websocket.query_params.get("token")
    if DASHBOARD_TOKEN and token != DASHBOARD_TOKEN:
        await websocket.close(code=1008); return
    await websocket.accept()
    try:
        while True:
            prices = load("data/market/ws_prices.json", {})
            await websocket.send_json(prices)
            await asyncio.sleep(5)
    except: pass


@app.post("/api/ai/ask")
async def ai_ask(request: Request):
    check_token(request)
    body = await request.json()
    prompt = body.get("prompt", "")
    # Use key from request header, fall back to server key
    api_key = request.headers.get("X-Anthropic-Key") or ENV.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(400, "No Anthropic API key available")
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}]
    )
    return {"text": response.content[0].text}

if __name__ == "__main__":
    uvicorn.run("dashboard_api:app", host="0.0.0.0", port=8080, reload=False, workers=1)
