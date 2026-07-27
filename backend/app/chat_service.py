import json
import os
import re
from typing import Generator
from openai import OpenAI
from app.db import get_connection, init_tables
from app.fund_service import FundService
from app.industry_service import IndustryService

# 中转服务配置
API_KEY = "your_api_key_here"
BASE_URL = "your_base_url_here"
MODEL = "glm-5.1"

# 加载知识库（模块级，只加载一次）
KNOWLEDGE_DIR = os.path.join(os.path.dirname(__file__), "knowledge")


def _load_knowledge() -> str:
    parts = []
    for filename in ["method.md", "scorecard.md"]:
        filepath = os.path.join(KNOWLEDGE_DIR, filename)
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                parts.append(f"## {filename}\n{f.read()}")
    return "\n\n".join(parts)


KNOWLEDGE_BASE = _load_knowledge()

SYSTEM_PROMPT = f"""你是一个专业的基金和股票分析助手。你只能回答与基金、股票、投资相关的问题。

如果用户的问题与基金、股票、投资无关，请礼貌地拒绝并引导用户提出基金或股票相关的问题。

以下是你的专业知识库，请基于此回答用户的问题：

{KNOWLEDGE_BASE}

重要：当你需要分析某只基金时，系统会自动注入该基金的实时数据（基本信息、持仓、行业分布、净值回撤等），请基于这些真实数据回答，不要编造数据。
"""


def _extract_fund_code(message: str) -> str | None:
    """从用户消息中提取基金代码（6位连续数字）"""
    match = re.search(r'(\d{6})', message)
    return match.group(1) if match else None


class ChatService:
    def __init__(self):
        self.client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
        self.fund_service = FundService()
        self.industry_service = IndustryService()

    def _inject_fund_data(self, user_message: str) -> str:
        """如果消息包含基金代码，自动注入该基金的实时数据（并发获取）"""
        code = _extract_fund_code(user_message)
        if not code:
            return user_message

        from concurrent.futures import ThreadPoolExecutor, as_completed
        tasks = {
            '基本信息': lambda: self.fund_service.search_fund(code),
            '持仓行业分布': lambda: self.industry_service.analyze_fund_industry(code),
            '近15日收益': lambda: self.fund_service.get_recent_returns(code),
            '净值与回撤': lambda: self.fund_service.get_nav_history(code, "1y"),
        }

        results = {}
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(fn): label for label, fn in tasks.items()}
            for future in as_completed(futures):
                label = futures[future]
                try:
                    results[label] = future.result()
                except Exception:
                    pass

        data_parts = []
        if '基本信息' in results:
            data_parts.append(f"【基金基本信息】\n{json.dumps(results['基本信息'], ensure_ascii=False)}")
        if '持仓行业分布' in results:
            data_parts.append(f"【持仓行业分布】\n{json.dumps(results['持仓行业分布'], ensure_ascii=False)}")
        if '近15日收益' in results:
            data_parts.append(f"【近15日收益】\n{json.dumps(results['近15日收益'], ensure_ascii=False)}")
        if '净值与回撤' in results:
            nav = results['净值与回撤']
            nav_summary = {
                "fund_code": nav["fund_code"],
                "period": nav["period"],
                "max_drawdown": nav["max_drawdown"],
                "nav_data_count": len(nav["nav_data"]),
                "latest_nav": nav["nav_data"][-1]["nav"] if nav["nav_data"] else None,
                "latest_date": nav["nav_data"][-1]["date"] if nav["nav_data"] else None,
            }
            data_parts.append(f"【净值与回撤】\n{json.dumps(nav_summary, ensure_ascii=False)}")

        if not data_parts:
            return user_message

        fund_data = "\n\n".join(data_parts)
        return f"{user_message}\n\n---系统注入的基金实时数据---\n{fund_data}\n---数据结束---"

    def _build_messages(self, session_id: str, user_message: str) -> list[dict]:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        history = self._get_history(session_id, limit=10)
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        # 当前消息注入基金数据
        enriched_message = self._inject_fund_data(user_message)
        messages.append({"role": "user", "content": enriched_message})
        return messages

    def stream_chat(self, session_id: str, user_message: str) -> Generator[str, None, None]:
        """流式聊天，逐 token 返回 SSE 数据"""
        messages = self._build_messages(session_id, user_message)

        # 保存原始用户消息（不含注入数据）
        self._save_message(session_id, "user", user_message)

        full_response = ""
        response = self.client.chat.completions.create(
            model=MODEL,
            messages=messages,
            stream=True,
            temperature=0.7,
            max_tokens=2048,
        )

        for chunk in response:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                full_response += token
                yield json.dumps({"token": token}, ensure_ascii=False)

        # 保存助手回复
        self._save_message(session_id, "assistant", full_response)
        yield json.dumps({"done": True}, ensure_ascii=False)

    def _save_message(self, session_id: str, role: str, content: str):
        init_tables()
        conn = get_connection()
        from datetime import datetime
        conn.execute(
            "INSERT INTO chat_messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, content, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()

    def _get_history(self, session_id: str, limit: int = 10) -> list[dict]:
        init_tables()
        conn = get_connection()
        rows = conn.execute(
            "SELECT role, content FROM chat_messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (session_id, limit)
        ).fetchall()
        conn.close()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def get_history(self, session_id: str) -> list[dict]:
        init_tables()
        conn = get_connection()
        rows = conn.execute(
            "SELECT role, content, created_at FROM chat_messages WHERE session_id = ? ORDER BY created_at",
            (session_id,)
        ).fetchall()
        conn.close()
        return [{"role": r["role"], "content": r["content"], "created_at": r["created_at"]} for r in rows]

    def clear_session(self, session_id: str):
        init_tables()
        conn = get_connection()
        conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
        conn.commit()
        conn.close()
