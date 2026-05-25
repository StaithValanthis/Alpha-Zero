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
import httpx
import uvicorn, asyncio

B = Path(os.path.expanduser("~/btc-agents"))

app = FastAPI(docs_url=None, redoc_url=None)
from fastapi.staticfiles import StaticFiles as _SF
import os as _os
_ap = "/home/btc-agent/pixel-agents/dist/assets"
if _os.path.exists(_ap):
    app.mount("/pixel-assets", _SF(directory=_ap), name="pixel-assets")

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


@app.get("/api/chief-status")
async def api_chief_status(request: Request):
    check_token(request)
    pipe = load("state/pipeline_state.json", {})
    queue = load("signals/trigger_queue.json", {"queue": []})
    anomaly = load("state/anomaly_state.json", {})
    sys_state = load("state/system_state.json", {})
    portfolio = load("state/portfolio.json", {})

    completed  = pipe.get("completed_today", [])
    in_progress = pipe.get("in_progress")
    scheduled  = pipe.get("scheduled_today", [])
    pending_triggers = [t for t in queue.get("queue", []) if t.get("status") == "pending"]
    risk_review      = [t for t in queue.get("queue", []) if t.get("status") == "risk_review"]
    executing        = [t for t in queue.get("queue", []) if t.get("status") == "executing"]

    import time as _time
    guardian_age = None
    hb = B / "services/position_guardian.heartbeat"
    if hb.exists():
        guardian_age = int(_time.time() - hb.stat().st_mtime)

    activity  = "Monitoring the queue..."
    animation = "idle"
    urgency   = "normal"
    subtitle  = f"Day {sys_state.get('cold_start_day', 0)}/14 · {len(completed)}/{len(scheduled)} tasks done today"

    circuit = portfolio.get("circuit_breaker_tripped", False)
    if circuit:
        activity  = "CIRCUIT BREAKER TRIPPED — all trading halted. Awaiting manual review."
        animation = "alarmed"; urgency = "critical"
    elif executing:
        t = executing[0]
        activity  = f"Trade executing — {t.get('strategy_id','?')}! Watching position..."
        animation = "alert"; urgency = "high"
    elif risk_review:
        t = risk_review[0]
        activity  = f"Delegated {t.get('trigger_id','?')[-8:]} to Risk Manager. Awaiting verdict..."
        animation = "delegating"; urgency = "medium"
    elif pending_triggers:
        activity  = f"{len(pending_triggers)} trigger(s) in queue — routing to Risk Manager now..."
        animation = "delegating"; urgency = "medium"
    elif anomaly.get("current_anomalies"):
        activity  = "Anomaly detected. Signal Watcher paused. Monitoring closely..."
        animation = "alert"; urgency = "high"
    elif in_progress == "analysts_parallel":
        activity  = "4 analysts running in parallel. Waiting for sync..."
        animation = "typing"
    elif in_progress == "hypothesis-generator":
        activity  = "Hypothesis Generator building trade ideas from analyst reports..."
        animation = "typing"
    elif in_progress in ("bull-researcher","bear-researcher"):
        activity  = "Bull and Bear debating in the chamber. Round 1 underway..."
        animation = "delegating"
    elif in_progress == "synthesis":
        activity  = "Synthesis Agent adjudicating the debate. Checking facts..."
        animation = "alert"
    elif in_progress == "strategy-tester":
        activity  = "Strategy Tester running walk-forward backtests..."
        animation = "typing"
    elif in_progress == "trader-management":
        activity  = "Trader/Management reconciling positions and durations..."
        animation = "typing"
    elif in_progress == "reporter":
        activity  = "Reporter compiling daily summary for Discord..."
        animation = "typing"
    elif in_progress == "orchestrator":
        activity  = "Orchestrator setting strategic direction. Writing directive..."
        animation = "typing"
    elif in_progress:
        activity  = f"Delegating to {in_progress.replace('-', ' ').title()}..."
        animation = "delegating"
    else:
        remaining = [s for s in scheduled if s not in completed]
        task_times = {
            "orchestrator":"01:30","analysts_parallel":"10:30",
            "hypothesis-generator":"10:35","strategy-tester":"12:30",
            "trader-management":"13:00","reporter":"19:00","journal-agent":"20:00"
        }
        if remaining:
            nxt = remaining[0]
            t   = task_times.get(nxt, "soon")
            activity  = f"All clear. Next up: {nxt.replace('-',' ').title()} at {t} AEST"
            animation = "idle"
        else:
            activity  = "All tasks complete for today. See you tomorrow at 01:30 AEST."
            animation = "celebrating"

    return {
        "activity": activity, "animation": animation,
        "urgency": urgency,   "subtitle": subtitle,
        "in_progress": in_progress,
        "completed_count": len(completed),
        "scheduled_count": len(scheduled),
        "pending_triggers": len(pending_triggers),
        "guardian_age_seconds": guardian_age,
        "circuit_breaker": circuit
    }


@app.get("/api/chief-status")
async def api_chief_status(request: Request):
    check_token(request)
    pipe = load("state/pipeline_state.json", {})
    queue = load("signals/trigger_queue.json", {"queue": []})
    anomaly = load("state/anomaly_state.json", {})
    sys_state = load("state/system_state.json", {})
    portfolio = load("state/portfolio.json", {})

    completed  = pipe.get("completed_today", [])
    in_progress = pipe.get("in_progress")
    scheduled  = pipe.get("scheduled_today", [])
    pending_triggers = [t for t in queue.get("queue", []) if t.get("status") == "pending"]
    risk_review      = [t for t in queue.get("queue", []) if t.get("status") == "risk_review"]
    executing        = [t for t in queue.get("queue", []) if t.get("status") == "executing"]

    import time as _time
    guardian_age = None
    hb = B / "services/position_guardian.heartbeat"
    if hb.exists():
        guardian_age = int(_time.time() - hb.stat().st_mtime)

    activity  = "Monitoring the queue..."
    animation = "idle"
    urgency   = "normal"
    subtitle  = f"Day {sys_state.get('cold_start_day', 0)}/14 · {len(completed)}/{len(scheduled)} tasks done today"

    circuit = portfolio.get("circuit_breaker_tripped", False)
    if circuit:
        activity  = "CIRCUIT BREAKER TRIPPED — all trading halted. Awaiting manual review."
        animation = "alarmed"; urgency = "critical"
    elif executing:
        t = executing[0]
        activity  = f"Trade executing — {t.get('strategy_id','?')}! Watching position..."
        animation = "alert"; urgency = "high"
    elif risk_review:
        t = risk_review[0]
        activity  = f"Delegated {t.get('trigger_id','?')[-8:]} to Risk Manager. Awaiting verdict..."
        animation = "delegating"; urgency = "medium"
    elif pending_triggers:
        activity  = f"{len(pending_triggers)} trigger(s) in queue — routing to Risk Manager now..."
        animation = "delegating"; urgency = "medium"
    elif anomaly.get("current_anomalies"):
        activity  = "Anomaly detected. Signal Watcher paused. Monitoring closely..."
        animation = "alert"; urgency = "high"
    elif in_progress == "analysts_parallel":
        activity  = "4 analysts running in parallel. Waiting for sync..."
        animation = "typing"
    elif in_progress == "hypothesis-generator":
        activity  = "Hypothesis Generator building trade ideas from analyst reports..."
        animation = "typing"
    elif in_progress in ("bull-researcher","bear-researcher"):
        activity  = "Bull and Bear debating in the chamber. Round 1 underway..."
        animation = "delegating"
    elif in_progress == "synthesis":
        activity  = "Synthesis Agent adjudicating the debate. Checking facts..."
        animation = "alert"
    elif in_progress == "strategy-tester":
        activity  = "Strategy Tester running walk-forward backtests..."
        animation = "typing"
    elif in_progress == "trader-management":
        activity  = "Trader/Management reconciling positions and durations..."
        animation = "typing"
    elif in_progress == "reporter":
        activity  = "Reporter compiling daily summary for Discord..."
        animation = "typing"
    elif in_progress == "orchestrator":
        activity  = "Orchestrator setting strategic direction. Writing directive..."
        animation = "typing"
    elif in_progress:
        activity  = f"Delegating to {in_progress.replace('-', ' ').title()}..."
        animation = "delegating"
    else:
        remaining = [s for s in scheduled if s not in completed]
        task_times = {
            "orchestrator":"01:30","analysts_parallel":"10:30",
            "hypothesis-generator":"10:35","strategy-tester":"12:30",
            "trader-management":"13:00","reporter":"19:00","journal-agent":"20:00"
        }
        if remaining:
            nxt = remaining[0]
            t   = task_times.get(nxt, "soon")
            activity  = f"All clear. Next up: {nxt.replace('-',' ').title()} at {t} AEST"
            animation = "idle"
        else:
            activity  = "All tasks complete for today. See you tomorrow at 01:30 AEST."
            animation = "celebrating"

    return {
        "activity": activity, "animation": animation,
        "urgency": urgency,   "subtitle": subtitle,
        "in_progress": in_progress,
        "completed_count": len(completed),
        "scheduled_count": len(scheduled),
        "pending_triggers": len(pending_triggers),
        "guardian_age_seconds": guardian_age,
        "circuit_breaker": circuit
    }


@app.get("/api/chief-status")
async def api_chief_status(request: Request):
    check_token(request)
    pipe      = load("state/pipeline_state.json", {})
    queue     = load("signals/trigger_queue.json", {"queue": []})
    anomaly   = load("state/anomaly_state.json", {})
    sys_state = load("state/system_state.json", {})
    portfolio = load("state/portfolio.json", {})

    completed        = pipe.get("completed_today", [])
    in_progress      = pipe.get("in_progress")
    scheduled        = pipe.get("scheduled_today", [])
    pending_triggers = [t for t in queue.get("queue", []) if t.get("status") == "pending"]
    risk_review      = [t for t in queue.get("queue", []) if t.get("status") == "risk_review"]
    executing        = [t for t in queue.get("queue", []) if t.get("status") == "executing"]

    import time as _t
    guardian_age = None
    hb = B / "services/position_guardian.heartbeat"
    if hb.exists():
        guardian_age = int(_t.time() - hb.stat().st_mtime)

    activity  = "Monitoring the queue..."
    animation = "idle"
    urgency   = "normal"
    circuit   = portfolio.get("circuit_breaker_tripped", False)

    if circuit:
        activity  = "CIRCUIT BREAKER TRIPPED — all trading halted. Awaiting manual review."
        animation = "alarmed"; urgency = "critical"
    elif executing:
        t = executing[0]
        activity  = "Trade executing — " + t.get("strategy_id","?") + "! Watching position..."
        animation = "alert"; urgency = "high"
    elif risk_review:
        t = risk_review[0]
        tid = t.get("trigger_id","?")[-8:]
        activity  = "Delegated " + tid + " to Risk Manager. Awaiting verdict..."
        animation = "delegating"; urgency = "medium"
    elif pending_triggers:
        n = len(pending_triggers)
        activity  = str(n) + " trigger(s) in queue — routing to Risk Manager now..."
        animation = "delegating"; urgency = "medium"
    elif anomaly.get("current_anomalies"):
        activity  = "Anomaly detected. Signal Watcher paused. Monitoring closely..."
        animation = "alert"; urgency = "high"
    elif in_progress == "analysts_parallel":
        activity  = "4 analysts running in parallel. Waiting for sync..."
        animation = "typing"
    elif in_progress == "hypothesis-generator":
        activity  = "Hypothesis Generator building trade ideas from analyst reports..."
        animation = "typing"
    elif in_progress in ("bull-researcher", "bear-researcher"):
        activity  = "Bull and Bear debating in the chamber. Round underway..."
        animation = "delegating"
    elif in_progress == "synthesis":
        activity  = "Synthesis Agent adjudicating the debate. Checking facts..."
        animation = "alert"
    elif in_progress == "strategy-tester":
        activity  = "Strategy Tester running walk-forward backtests..."
        animation = "typing"
    elif in_progress == "trader-management":
        activity  = "Trader/Management reconciling positions and durations..."
        animation = "typing"
    elif in_progress == "reporter":
        activity  = "Reporter compiling daily summary for Discord..."
        animation = "typing"
    elif in_progress == "orchestrator":
        activity  = "Orchestrator setting strategic direction. Writing directive..."
        animation = "typing"
    elif in_progress:
        activity  = "Delegating to " + in_progress.replace("-", " ").title() + "..."
        animation = "delegating"
    else:
        task_times = {
            "orchestrator": "01:30", "analysts_parallel": "10:30",
            "hypothesis-generator": "10:35", "strategy-tester": "12:30",
            "trader-management": "13:00", "reporter": "19:00",
            "journal-agent": "20:00"
        }
        remaining = [s for s in scheduled if s not in completed]
        if remaining:
            nxt = remaining[0]
            t   = task_times.get(nxt, "soon")
            activity  = "All clear. Next: " + nxt.replace("-", " ").title() + " at " + t + " AEST"
            animation = "idle"
        else:
            activity  = "All tasks complete for today. See you tomorrow at 01:30 AEST."
            animation = "celebrating"

    return {
        "activity":          activity,
        "animation":         animation,
        "urgency":           urgency,
        "in_progress":       in_progress,
        "completed_count":   len(completed),
        "scheduled_count":   len(scheduled),
        "pending_triggers":  len(pending_triggers),
        "guardian_age_seconds": guardian_age,
        "circuit_breaker":   circuit
    }


@app.get("/api/chief-status")
async def api_chief_status(request: Request):
    check_token(request)
    pipe = load("state/pipeline_state.json", {})
    queue = load("signals/trigger_queue.json", {"queue": []})
    anomaly = load("state/anomaly_state.json", {})
    sys_state = load("state/system_state.json", {})
    portfolio = load("state/portfolio.json", {})

    completed  = pipe.get("completed_today", [])
    in_progress = pipe.get("in_progress")
    scheduled  = pipe.get("scheduled_today", [])
    pending_triggers = [t for t in queue.get("queue", []) if t.get("status") == "pending"]
    risk_review      = [t for t in queue.get("queue", []) if t.get("status") == "risk_review"]
    executing        = [t for t in queue.get("queue", []) if t.get("status") == "executing"]

    import time as _time
    guardian_age = None
    hb = B / "services/position_guardian.heartbeat"
    if hb.exists():
        guardian_age = int(_time.time() - hb.stat().st_mtime)

    activity  = "Monitoring the queue..."
    animation = "idle"
    urgency   = "normal"
    subtitle  = f"Day {sys_state.get('cold_start_day', 0)}/14 · {len(completed)}/{len(scheduled)} tasks done today"

    circuit = portfolio.get("circuit_breaker_tripped", False)
    if circuit:
        activity  = "CIRCUIT BREAKER TRIPPED — all trading halted. Awaiting manual review."
        animation = "alarmed"; urgency = "critical"
    elif executing:
        t = executing[0]
        activity  = f"Trade executing — {t.get('strategy_id','?')}! Watching position..."
        animation = "alert"; urgency = "high"
    elif risk_review:
        t = risk_review[0]
        activity  = f"Delegated {t.get('trigger_id','?')[-8:]} to Risk Manager. Awaiting verdict..."
        animation = "delegating"; urgency = "medium"
    elif pending_triggers:
        activity  = f"{len(pending_triggers)} trigger(s) in queue — routing to Risk Manager now..."
        animation = "delegating"; urgency = "medium"
    elif anomaly.get("current_anomalies"):
        activity  = "Anomaly detected. Signal Watcher paused. Monitoring closely..."
        animation = "alert"; urgency = "high"
    elif in_progress == "analysts_parallel":
        activity  = "4 analysts running in parallel. Waiting for sync..."
        animation = "typing"
    elif in_progress == "hypothesis-generator":
        activity  = "Hypothesis Generator building trade ideas from analyst reports..."
        animation = "typing"
    elif in_progress in ("bull-researcher","bear-researcher"):
        activity  = "Bull and Bear debating in the chamber. Round 1 underway..."
        animation = "delegating"
    elif in_progress == "synthesis":
        activity  = "Synthesis Agent adjudicating the debate. Checking facts..."
        animation = "alert"
    elif in_progress == "strategy-tester":
        activity  = "Strategy Tester running walk-forward backtests..."
        animation = "typing"
    elif in_progress == "trader-management":
        activity  = "Trader/Management reconciling positions and durations..."
        animation = "typing"
    elif in_progress == "reporter":
        activity  = "Reporter compiling daily summary for Discord..."
        animation = "typing"
    elif in_progress == "orchestrator":
        activity  = "Orchestrator setting strategic direction. Writing directive..."
        animation = "typing"
    elif in_progress:
        activity  = f"Delegating to {in_progress.replace('-', ' ').title()}..."
        animation = "delegating"
    else:
        remaining = [s for s in scheduled if s not in completed]
        task_times = {
            "orchestrator":"01:30","analysts_parallel":"10:30",
            "hypothesis-generator":"10:35","strategy-tester":"12:30",
            "trader-management":"13:00","reporter":"19:00","journal-agent":"20:00"
        }
        if remaining:
            nxt = remaining[0]
            t   = task_times.get(nxt, "soon")
            activity  = f"All clear. Next up: {nxt.replace('-',' ').title()} at {t} AEST"
            animation = "idle"
        else:
            activity  = "All tasks complete for today. See you tomorrow at 01:30 AEST."
            animation = "celebrating"

    return {
        "activity": activity, "animation": animation,
        "urgency": urgency,   "subtitle": subtitle,
        "in_progress": in_progress,
        "completed_count": len(completed),
        "scheduled_count": len(scheduled),
        "pending_triggers": len(pending_triggers),
        "guardian_age_seconds": guardian_age,
        "circuit_breaker": circuit
    }


@app.get("/office/{path:path}")
async def office_proxy(path: str, request: Request):
    """Proxy the pixel-agents office through FastAPI so no extra port needed."""
    url = f"http://127.0.0.1:8082/{path}"
    if request.query_params:
        url += "?" + str(request.query_params)
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, timeout=10)
            from fastapi.responses import Response
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                media_type=resp.headers.get("content-type", "text/html")
            )
        except Exception:
            return Response("Pixel office unavailable", status_code=503)

@app.get("/office")
async def office_root(request: Request):
    return await office_proxy("", request)


@app.websocket("/ws")
async def ws_proxy(websocket: WebSocket):
    """Proxy WebSocket from pixel-agents server through port 8080."""
    import websockets as _ws
    await websocket.accept()
    try:
        async with _ws.connect("ws://127.0.0.1:8082/ws") as backend:
            async def forward_to_backend():
                async for msg in websocket.iter_text():
                    await backend.send(msg)
            async def forward_to_client():
                async for msg in backend:
                    await websocket.send_text(msg)
            import asyncio
            done, pending = await asyncio.wait(
                [asyncio.ensure_future(forward_to_backend()),
                 asyncio.ensure_future(forward_to_client())],
                return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
    except Exception:
        pass


@app.websocket("/ws/agents")
async def ws_agent_states(websocket: WebSocket):
    """Push agent states every 3 seconds for the pixel office."""
    check_token(websocket)
    await websocket.accept()
    try:
        while True:
            pipe    = load("state/pipeline_state.json", {})
            syslog  = load("state/system-log.json", {"entries": []})
            anomaly = load("state/anomaly_state.json", {})

            completed  = pipe.get("completed_today", [])
            in_progress = pipe.get("in_progress")
            today = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%d")
            entries = [e for e in (syslog.get("entries", []) if isinstance(syslog, dict) else [])
                       if e.get("timestamp", "").startswith(today)]
            ran_today = {e["agent"] for e in entries if e.get("status") == "success"}

            def state(agent_id):
                if in_progress and agent_id in in_progress:
                    return "working"
                if agent_id in ran_today:
                    return "done"
                return "idle"

            agents = [
                {"id":"chief",      "name":"Chief",      "char":0, "state":"working"},
                {"id":"orchestrator","name":"Orchestrator","char":1,"state":state("orchestrator")},
                {"id":"bull",       "name":"Bull",       "char":2, "state":state("bull-researcher")},
                {"id":"bear",       "name":"Bear",       "char":3, "state":state("bear-researcher")},
                {"id":"synthesis",  "name":"Synthesis",  "char":4, "state":state("synthesis")},
                {"id":"risk",       "name":"Risk Mgr",   "char":5, "state":state("risk-manager")},
                {"id":"tech",       "name":"Tech",       "char":1, "state":state("technical-analyst")},
                {"id":"deriv",      "name":"Deriv",      "char":2, "state":state("derivatives-analyst")},
                {"id":"onchain",    "name":"OnChain",    "char":3, "state":state("onchain-macro-analyst")},
                {"id":"sentiment",  "name":"Sentiment",  "char":4, "state":state("sentiment-news-analyst")},
            ]

            circuit = load("state/portfolio.json", {}).get("circuit_breaker_tripped", False)
            await websocket.send_json({
                "agents": agents,
                "circuit_breaker": circuit,
                "in_progress": in_progress
            })
            await asyncio.sleep(3)
    except Exception:
        pass

@app.get("/office-page", response_class=HTMLResponse)
async def office_page(request: Request):
    check_token(request)
    p = B / "dashboard/office.html"
    return HTMLResponse(p.read_text() if p.exists() else "<h1>Office not found</h1>")


@app.get("/dashboard-static/{filename}")
async def dashboard_static(filename: str, request: Request):
    check_token(request)
    import mimetypes
    p = B / "dashboard" / filename
    if not p.exists(): raise HTTPException(404)
    mt = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
    from fastapi.responses import Response
    return Response(p.read_bytes(), media_type=mt)

if __name__ == "__main__":
    uvicorn.run("dashboard_api:app", host="0.0.0.0", port=8080, reload=False, workers=1)
