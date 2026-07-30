from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from app.db import get_connection, init_tables
from app.fund_service import FundService
from app.industry_service import IndustryService
from app.chat_service import ChatService

app = FastAPI(title="基金分析API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

fund_service = FundService()
industry_service = IndustryService()
chat_service = ChatService()


@app.get("/api/fund/search")
def search_fund(code: str = Query(...)):
    try:
        return fund_service.search_fund(code)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/fund/holdings")
def get_holdings(code: str = Query(...), date: str = Query(None)):
    try:
        return fund_service.get_holdings(code, date)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/fund/industry")
def get_fund_industry(code: str = Query(...), date: str = Query(None), fund_name: str = Query(None)):
    try:
        return industry_service.analyze_fund_industry(code, date, fund_name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/fund/nav")
def get_fund_nav(code: str = Query(...), period: str = Query("1y", description="时间周期: 1m,3m,6m,1y,3y")):
    try:
        return fund_service.get_nav_history(code, period)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/fund/returns")
def get_fund_returns(code: str = Query(...)):
    try:
        return fund_service.get_recent_returns(code)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/fund/bond-holdings")
def get_bond_holdings(code: str = Query(...), date: str = Query(None)):
    try:
        return fund_service.get_bond_holdings(code, date)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


# 自选基金接口
class WatchlistItem(BaseModel):
    code: str
    name: str


@app.post("/api/watchlist/add")
def add_watchlist(item: WatchlistItem):
    init_tables()
    conn = get_connection()
    from datetime import datetime
    conn.execute(
        "INSERT OR REPLACE INTO watchlist (fund_code, fund_name, added_at) VALUES (?, ?, ?)",
        (item.code, item.name, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return {"message": "添加成功", "code": item.code, "name": item.name}


@app.delete("/api/watchlist/remove")
def remove_watchlist(code: str = Query(...)):
    init_tables()
    conn = get_connection()
    conn.execute("DELETE FROM watchlist WHERE fund_code = ?", (code,))
    conn.commit()
    conn.close()
    return {"message": "删除成功", "code": code}


@app.get("/api/watchlist/list")
def list_watchlist():
    init_tables()
    conn = get_connection()
    rows = conn.execute("SELECT fund_code, fund_name, added_at, position_amount, profit_amount, cost_nav, cost_nav_date, position_updated_at FROM watchlist ORDER BY added_at DESC").fetchall()
    conn.close()

    # 批量获取持仓基金的最新净值（15分钟缓存）
    holding_codes = [r["fund_code"] for r in rows if (r["position_amount"] or 0) > 0 and (r["cost_nav"] or 0) > 0]
    nav_cache = _get_latest_navs(holding_codes)

    result = []
    for r in rows:
        pos = r["position_amount"] or 0       # 用户输入的余额
        prof = r["profit_amount"] or 0        # 用户输入的收益
        cost_nav = r["cost_nav"] or 0
        cost_nav_date = r["cost_nav_date"]    # 记录时的净值日期
        is_holding = pos > 0 and cost_nav > 0

        if is_holding:
            nav_info = nav_cache.get(r["fund_code"])
            latest_nav = nav_info["nav"] if nav_info else None
            latest_date = nav_info["date"] if nav_info else None

            # 只有净值日期变化时才重新计算
            if latest_nav and cost_nav > 0 and latest_date and latest_date != cost_nav_date:
                nav_change = latest_nav / cost_nav
                balance = round(pos * nav_change, 2)
                cost = pos - prof
                current_cost = round(cost * nav_change, 2)
                profit = round(balance - current_cost, 2)
                profit_rate = round(profit / current_cost * 100, 2) if current_cost > 0 else 0
            else:
                # 日期未变，使用原始数据
                balance = pos
                profit = prof
                profit_rate = round(prof / (pos - prof) * 100, 2) if (pos - prof) > 0 else 0
        else:
            balance = None
            profit = None
            profit_rate = None

        item = {
            "code": r["fund_code"],
            "name": r["fund_name"],
            "added_at": r["added_at"],
            "position_amount": pos,
            "balance": balance,
            "profit": profit,
            "profit_rate": profit_rate,
            "is_holding": is_holding,
        }
        result.append(item)
    return result


# 净值缓存：15分钟
_nav_cache: dict = {}
_nav_cache_time: float = 0
_NAV_CACHE_TTL = 900  # 15分钟


def _get_latest_navs(codes: list[str]) -> dict:
    """批量获取最新净值和日期，15分钟缓存"""
    global _nav_cache, _nav_cache_time
    import time
    now = time.time()

    if not codes:
        return {}

    # 缓存未过期，直接返回
    if _nav_cache and now - _nav_cache_time < _NAV_CACHE_TTL:
        return {c: _nav_cache.get(c) for c in codes if c in _nav_cache}

    # 重新获取
    _nav_cache = {}
    for code in codes:
        try:
            info = fund_service.search_fund(code)
            nav = info.get("latest_nav")
            nav_date = info.get("latest_date")
            if nav:
                _nav_cache[code] = {"nav": nav, "date": nav_date}
        except Exception:
            pass
    _nav_cache_time = now
    return {c: _nav_cache.get(c) for c in codes if c in _nav_cache}


class PositionRequest(BaseModel):
    code: str
    position_amount: float  # 当前余额
    profit: float           # 当前收益（负数=亏损）


@app.put("/api/watchlist/position")
def update_position(req: PositionRequest):
    init_tables()
    conn = get_connection()
    from datetime import datetime

    balance = req.position_amount
    profit = req.profit

    # 记录当前净值和净值日期作为基准
    cost_nav = 0
    cost_nav_date = None
    if balance > 0:
        try:
            fund_info = fund_service.search_fund(req.code)
            cost_nav = fund_info.get("latest_nav", 0) or 0
            cost_nav_date = fund_info.get("latest_date")
        except Exception:
            pass

    # 清除持仓
    if balance <= 0:
        balance = 0
        profit = 0
        cost_nav = 0
        cost_nav_date = None

    conn.execute(
        "UPDATE watchlist SET position_amount = ?, profit_amount = ?, cost_nav = ?, cost_nav_date = ?, position_updated_at = ? WHERE fund_code = ?",
        (balance, profit, cost_nav, cost_nav_date, datetime.now().isoformat(), req.code)
    )
    conn.commit()
    conn.close()
    return {"message": "持仓更新成功", "code": req.code, "cost_nav": cost_nav, "cost_nav_date": cost_nav_date}


# AI 聊天接口
class ChatRequest(BaseModel):
    session_id: str
    message: str


@app.post("/api/chat/send")
def chat_send(req: ChatRequest):
    """SSE 流式聊天"""
    def event_generator():
        for chunk in chat_service.stream_chat(req.session_id, req.message):
            yield dict(data=chunk)
    return EventSourceResponse(event_generator(), ping=None)


@app.get("/api/chat/history")
def chat_history(session_id: str = Query(...)):
    return chat_service.get_history(session_id)


@app.delete("/api/chat/clear")
def chat_clear(session_id: str = Query(...)):
    chat_service.clear_session(session_id)
    return {"message": "已清除对话记录"}
