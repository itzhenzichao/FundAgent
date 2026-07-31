import json
import os
from typing import Generator
from openai import OpenAI
from app.db import get_connection, init_tables
from app.tools import TOOLS, execute_tool, TOOL_NAME_MAP
from app.config import API_KEY, BASE_URL, MODEL, MAX_TOOL_ROUNDS

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

重要：
- 当你需要分析某只基金时，请使用提供的工具来获取实时数据，不要编造数据。
- 你可以同时调用多个工具来获取不同数据。
- 当用户问"我的自选""我的持仓""我关注的基金"时，请使用 get_watchlist 工具。
- 当用户提到多只基金时，请分别调用工具获取每只基金的数据。
"""


class ChatService:
    def __init__(self):
        self.client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    def _build_messages(self, session_id: str, user_message: str) -> list[dict]:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        history = self._get_history(session_id, limit=10)
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_message})
        return messages

    def stream_chat(self, session_id: str, user_message: str) -> Generator[str, None, None]:
        """流式聊天，支持工具调用循环"""
        messages = self._build_messages(session_id, user_message)
        self._save_message(session_id, "user", user_message)

        for _ in range(MAX_TOOL_ROUNDS):
            try:
                response = self.client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    tools=TOOLS,
                    stream=True,
                    temperature=0.7,
                    max_tokens=2048,
                )
            except Exception as e:
                # LLM 不支持 tools 参数，降级为无工具调用
                if "tools" in str(e).lower() or "function" in str(e).lower() or "tool" in str(e).lower():
                    yield from self._stream_without_tools(messages, session_id)
                    return
                raise

            tool_calls, content_tokens = self._process_stream(response)

            if tool_calls:
                # 发送工具调用通知
                for tc in tool_calls:
                    fn_name = tc["function"]["name"]
                    try:
                        fn_args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        fn_args = {}

                    yield json.dumps({
                        "tool_call": {
                            "name": fn_name,
                            "label": TOOL_NAME_MAP.get(fn_name, fn_name),
                            "arguments": fn_args,
                        }
                    }, ensure_ascii=False)

                # 执行工具调用
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": tool_calls,
                })

                for tc in tool_calls:
                    fn_name = tc["function"]["name"]
                    try:
                        fn_args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        fn_args = {}

                    result = execute_tool(fn_name, fn_args)

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result,
                    })

                continue

            # 无工具调用 → 最终文本回复
            full_response = ""
            for token in content_tokens:
                full_response += token
                yield json.dumps({"token": token}, ensure_ascii=False)

            self._save_message(session_id, "assistant", full_response)
            yield json.dumps({"done": True}, ensure_ascii=False)
            return

        # 超过最大轮次，强制无工具回复
        yield from self._stream_without_tools(messages, session_id)

    def _stream_without_tools(self, messages: list[dict], session_id: str) -> Generator[str, None, None]:
        """无工具调用的流式回复（降级方案）"""
        response = self.client.chat.completions.create(
            model=MODEL,
            messages=messages,
            stream=True,
            temperature=0.7,
            max_tokens=2048,
        )
        full_response = ""
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                full_response += token
                yield json.dumps({"token": token}, ensure_ascii=False)
        self._save_message(session_id, "assistant", full_response)
        yield json.dumps({"done": True}, ensure_ascii=False)

    def _process_stream(self, response) -> tuple[list[dict], list[str]]:
        """处理流式响应，区分工具调用和文本内容"""
        tool_call_buffers: dict[int, dict] = {}
        content_tokens: list[str] = []

        for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            if delta.content:
                content_tokens.append(delta.content)

            if delta.tool_calls:
                for tc_chunk in delta.tool_calls:
                    idx = tc_chunk.index
                    if idx not in tool_call_buffers:
                        tool_call_buffers[idx] = {
                            "id": "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    if tc_chunk.id:
                        tool_call_buffers[idx]["id"] = tc_chunk.id
                    if tc_chunk.function:
                        if tc_chunk.function.name:
                            tool_call_buffers[idx]["function"]["name"] += tc_chunk.function.name
                        if tc_chunk.function.arguments:
                            tool_call_buffers[idx]["function"]["arguments"] += tc_chunk.function.arguments

        if tool_call_buffers:
            return [tool_call_buffers[i] for i in sorted(tool_call_buffers.keys())], content_tokens
        return [], content_tokens

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
