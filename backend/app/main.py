from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from datetime import datetime
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
    global _nav_fetched_today, _nav_fetched_date

    init_tables()
    conn = get_connection()
    rows = conn.execute("SELECT fund_code, fund_name, added_at, position_amount, profit_amount, cost_nav, cost_nav_date, position_updated_at FROM watchlist ORDER BY added_at DESC").fetchall()

    # 跨天重置已查记录
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    if today_str != _nav_fetched_date:
        _nav_fetched_today = set()
        _nav_fetched_date = today_str
    after_2030 = now.hour > 20 or (now.hour == 20 and now.minute >= 30)

    codes_to_fetch = []
    for r in rows:
        pos = r["position_amount"] or 0
        cost_nav = r["cost_nav"] or 0
        cost_nav_date = r["cost_nav_date"]
        if pos <= 0 or cost_nav <= 0:
            continue
        # 非同一天：一定查
        if cost_nav_date != today_str:
            codes_to_fetch.append(r["fund_code"])
            continue
        # 同一天且 20:30 后：查一次（查过就不查了，通过 _nav_fetched_today 控制）
        if after_2030 and r["fund_code"] not in _nav_fetched_today:
            codes_to_fetch.append(r["fund_code"])

    nav_cache = _get_latest_navs(codes_to_fetch) if codes_to_fetch else {}

    # 标记今天已查过的基金
    for code in codes_to_fetch:
        if code in nav_cache:
            _nav_fetched_today.add(code)

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

            # 净值日期变化 → 重算并写回数据库
            if latest_nav and cost_nav > 0 and latest_date and latest_date != cost_nav_date:
                nav_change = latest_nav / cost_nav
                # 本金不变
                cost = pos - prof
                # 余额随净值变化
                balance = round(pos * nav_change, 2)
                # 收益 = 新余额 - 本金
                profit = round(balance - cost, 2)
                profit_rate = round(profit / cost * 100, 2) if cost > 0 else 0

                # 写回数据库：更新余额、收益、净值日期为新基准
                conn.execute(
                    "UPDATE watchlist SET position_amount = ?, profit_amount = ?, cost_nav = ?, cost_nav_date = ?, position_updated_at = ? WHERE fund_code = ?",
                    (balance, profit, latest_nav, latest_date, datetime.now().isoformat(), r["fund_code"])
                )
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
            "updated_at": r["cost_nav_date"] if is_holding else None,
            "position_amount": pos,
            "balance": balance,
            "profit": profit,
            "profit_rate": profit_rate,
            "is_holding": is_holding,
        }
        result.append(item)

    conn.commit()
    conn.close()
    return result


# 记录今天已查过新净值的基金（跨天重置）
_nav_fetched_today: set = set()
_nav_fetched_date: str = ""


def _get_latest_navs(codes: list[str]) -> dict:
    """批量获取最新净值和日期，绕过 search_fund 的1天缓存，直接调 akshare 拿最新值"""
    import akshare as ak
    import time

    if not codes:
        return {}

    result = {}
    for code in codes:
        try:
            df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
            if df.empty:
                continue
            latest = df.iloc[-1]
            cols = df.columns.tolist()
            nav_col = "单位净值" if "单位净值" in cols else cols[1] if len(cols) > 1 else None
            date_col = "净值日期" if "净值日期" in cols else cols[0] if len(cols) > 0 else None
            if nav_col and date_col:
                nav = float(latest[nav_col])
                date = str(latest[date_col].date()) if hasattr(latest[date_col], 'date') else str(latest[date_col])
                result[code] = {"nav": nav, "date": date}
        except Exception:
            pass
    return result


class PositionRequest(BaseModel):
    code: str
    position_amount: float  # 当前余额
    profit: float           # 当前收益（负数=亏损）


@app.put("/api/watchlist/position")
def update_position(req: PositionRequest):
    init_tables()
    conn = get_connection()

    balance = req.position_amount
    profit = req.profit

    # 记录当前净值和净值日期作为基准（直接调 akshare，不走缓存）
    cost_nav = 0
    cost_nav_date = None
    if balance > 0:
        try:
            import akshare as ak
            df = ak.fund_open_fund_info_em(symbol=req.code, indicator="单位净值走势")
            if not df.empty:
                latest = df.iloc[-1]
                cols = df.columns.tolist()
                nav_col = "单位净值" if "单位净值" in cols else cols[1] if len(cols) > 1 else None
                date_col = "净值日期" if "净值日期" in cols else cols[0] if len(cols) > 0 else None
                if nav_col and date_col:
                    cost_nav = float(latest[nav_col])
                    cost_nav_date = str(latest[date_col].date()) if hasattr(latest[date_col], 'date') else str(latest[date_col])
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
        try:
            for chunk in chat_service.stream_chat(req.session_id, req.message):
                yield dict(data=chunk)
        except Exception as e:
            import json
            yield dict(data=json.dumps({"error": str(e)}, ensure_ascii=False))
            yield dict(data=json.dumps({"done": True}, ensure_ascii=False))
    return EventSourceResponse(event_generator(), ping=15)


@app.get("/api/chat/history")
def chat_history(session_id: str = Query(...)):
    return chat_service.get_history(session_id)


@app.delete("/api/chat/clear")
def chat_clear(session_id: str = Query(...)):
    chat_service.clear_session(session_id)
    return {"message": "已清除对话记录"}
