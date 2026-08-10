import json
import os
import time
import logging
from typing import Generator
from openai import OpenAI
from app.db import get_connection, init_tables
from app.tools import TOOLS, execute_tool, TOOL_NAME_MAP
from app.config import API_KEY, BASE_URL, MODEL, MAX_TOOL_ROUNDS

logger = logging.getLogger("chat_perf")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [chat] %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(handler)
    logger.propagate = False

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

SYSTEM_PROMPT = """你是一个专业的基金和股票分析助手。你只能回答与基金、股票、投资相关的问题。

如果用户的问题与基金、股票、投资无关，请礼貌地拒绝。

重要：
- 使用提供的工具获取实时数据，不要编造数据。
- 分析单只基金时，请一次性同时调用所有相关工具（search_fund、get_fund_industry、get_fund_returns、get_fund_nav、get_fund_holdings），不要分多轮调用。
- 分析多只基金时，同样一次性并行调用每只基金的所有工具，避免分轮次。
- "我的自选""我的持仓""我关注的基金"相关问题使用 get_watchlist 工具。
- 回答要结构化、简洁，避免冗长重复；用 Markdown 表格和分点呈现关键数据。
- 投资建议需基于数据，给出明确理由，不做无依据的预测。
"""


def _trim_tool_result(result: str, max_len: int = 1200) -> str:
    """截断过长的工具结果，减少 messages 体积"""
    if len(result) <= max_len:
        return result
    # 保留前 900 字符（含主要数据）+ 截断提示 + 后 200 字符（含尾部摘要）
    return result[:900] + f"\n...(共{len(result)}字符，已截断中间部分)..." + result[-200:]


class ChatService:
    def __init__(self):
        self.client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    def _build_messages(self, session_id: str, user_message: str) -> list[dict]:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        history = self._get_history(session_id, limit=6)
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_message})
        return messages

    def stream_chat(self, session_id: str, user_message: str) -> Generator[str, None, None]:
        """流式聊天，支持工具调用循环"""
        t0 = time.time()
        logger.info(f"[T+0.00s] stream_chat started, msg={user_message[:50]}")

        messages = self._build_messages(session_id, user_message)
        # 估算 messages 总 token（粗算：中文 1 字≈1.5 token）
        total_chars = sum(len(m.get("content", "") or "") for m in messages)
        logger.info(f"[T+{time.time()-t0:.2f}s] messages built: {len(messages)} msgs, ~{total_chars} chars")

        self._save_message(session_id, "user", user_message)

        for round_idx in range(MAX_TOOL_ROUNDS):
            try:
                t_llm = time.time()
                response = self.client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    tools=TOOLS,
                    stream=True,
                    temperature=0.7,
                    max_tokens=4096,
                    timeout=60,
                )
                logger.info(f"[T+{time.time()-t0:.2f}s] round {round_idx}: LLM call started (model={MODEL}, tools={len(TOOLS)})")
            except Exception as e:
                if "tools" in str(e).lower() or "function" in str(e).lower() or "tool" in str(e).lower():
                    logger.info(f"[T+{time.time()-t0:.2f}s] round {round_idx}: LLM doesn't support tools, fallback")
                    yield from self._stream_without_tools(messages, session_id, t0)
                    return
                raise

            tool_calls, content_tokens, first_chunk_time = self._process_stream(response, t0, round_idx)
            t_stream_done = time.time()
            logger.info(
                f"[T+{t_stream_done-t0:.2f}s] round {round_idx}: stream done "
                f"(first_chunk={first_chunk_time-t_llm:.2f}s, stream_total={t_stream_done-t_llm:.2f}s, "
                f"tool_calls={len(tool_calls)}, content={len(''.join(content_tokens))} chars)"
            )

            if tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": tool_calls,
                })

                parsed_calls = []
                for tc in tool_calls:
                    fn_name = tc["function"]["name"]
                    try:
                        fn_args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        fn_args = {}
                    parsed_calls.append((tc, fn_name, fn_args))
                    logger.info(f"[T+{time.time()-t0:.2f}s] round {round_idx}: tool_call {fn_name}({fn_args})")

                for tc, fn_name, fn_args in parsed_calls:
                    yield json.dumps({
                        "tool_call": {
                            "name": fn_name,
                            "label": TOOL_NAME_MAP.get(fn_name, fn_name),
                            "arguments": fn_args,
                        }
                    }, ensure_ascii=False)

                t_tools = time.time()
                from concurrent.futures import ThreadPoolExecutor
                def _exec(args):
                    tc, fn_name, fn_args = args
                    t_start = time.time()
                    result = execute_tool(fn_name, fn_args)
                    logger.info(f"[T+{time.time()-t0:.2f}s]   {fn_name} done in {time.time()-t_start:.2f}s, result={len(result)} chars")
                    return tc, result

                with ThreadPoolExecutor(max_workers=4) as executor:
                    results = list(executor.map(_exec, parsed_calls))
                logger.info(f"[T+{time.time()-t0:.2f}s] round {round_idx}: all tools done in {time.time()-t_tools:.2f}s")

                for tc, result in results:
                    trimmed = _trim_tool_result(result)
                    if len(trimmed) < len(result):
                        logger.info(f"[T+{time.time()-t0:.2f}s]   trimmed tool result: {len(result)} -> {len(trimmed)} chars")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": trimmed,
                    })

                # 估算 messages 增长
                total_chars = sum(len(m.get("content", "") or "") for m in messages)
                logger.info(f"[T+{time.time()-t0:.2f}s] round {round_idx}: messages now {len(messages)} msgs, ~{total_chars} chars")

                continue

            full_response = ""
            for token in content_tokens:
                full_response += token
                yield json.dumps({"token": token}, ensure_ascii=False)

            self._save_message(session_id, "assistant", full_response)
            logger.info(f"[T+{time.time()-t0:.2f}s] final text: {len(full_response)} chars, done")
            yield json.dumps({"done": True}, ensure_ascii=False)
            return

        logger.info(f"[T+{time.time()-t0:.2f}s] max rounds reached, fallback to no-tools")
        yield from self._stream_without_tools(messages, session_id, t0)

    def _stream_without_tools(self, messages: list[dict], session_id: str, t0: float = None) -> Generator[str, None, None]:
        """无工具调用的流式回复（降级方案）"""
        if t0 is None:
            t0 = time.time()
        logger.info(f"[T+{time.time()-t0:.2f}s] _stream_without_tools started")
        response = self.client.chat.completions.create(
            model=MODEL,
            messages=messages,
            stream=True,
            temperature=0.7,
            max_tokens=4096,
            timeout=60,
        )
        full_response = ""
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                full_response += token
                yield json.dumps({"token": token}, ensure_ascii=False)
        self._save_message(session_id, "assistant", full_response)
        logger.info(f"[T+{time.time()-t0:.2f}s] _stream_without_tools done, {len(full_response)} chars")
        yield json.dumps({"done": True}, ensure_ascii=False)

    def _process_stream(self, response, t0: float = None, round_idx: int = 0) -> tuple[list[dict], list[str], float]:
        """处理流式响应，区分工具调用和文本内容"""
        if t0 is None:
            t0 = time.time()
        tool_call_buffers: dict[int, dict] = {}
        content_tokens: list[str] = []
        first_chunk_time = None

        for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            if first_chunk_time is None and (delta.content or delta.tool_calls):
                first_chunk_time = time.time()
                logger.info(f"[T+{first_chunk_time-t0:.2f}s] round {round_idx}: first chunk received")

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

        if first_chunk_time is None:
            first_chunk_time = time.time()

        if tool_call_buffers:
            return [tool_call_buffers[i] for i in sorted(tool_call_buffers.keys())], content_tokens, first_chunk_time
        return [], content_tokens, first_chunk_time

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

    def _get_history(self, session_id: str, limit: int = 6) -> list[dict]:
        init_tables()
        conn = get_connection()
        rows = conn.execute(
            "SELECT role, content FROM chat_messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (session_id, limit)
        ).fetchall()
        conn.close()
        result = []
        for r in reversed(rows):
            content = r["content"]
            # 截断过长的 assistant 回复，避免历史膨胀
            if r["role"] == "assistant" and len(content) > 600:
                content = content[:600] + f"\n\n...(原文{len(content)}字符已截断)"
            result.append({"role": r["role"], "content": content})
        return result

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
