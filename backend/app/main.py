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
    rows = conn.execute("SELECT fund_code, fund_name, added_at FROM watchlist ORDER BY added_at DESC").fetchall()
    conn.close()
    return [{"code": r["fund_code"], "name": r["fund_name"], "added_at": r["added_at"]} for r in rows]


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
