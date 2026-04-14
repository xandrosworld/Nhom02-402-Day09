"""
workers/policy_tool.py — Policy & Tool Worker
Sprint 2+3: Kiểm tra policy dựa vào context, gọi MCP tools khi cần.

Input (từ AgentState):
    - task: câu hỏi
    - retrieved_chunks: context từ retrieval_worker
    - needs_tool: True nếu supervisor quyết định cần tool call

Output (vào AgentState):
    - policy_result: {"policy_applies", "policy_name", "exceptions_found", "source", "rule"}
    - mcp_tools_used: list of tool calls đã thực hiện
    - worker_io_log: log

Gọi độc lập để test:
    python workers/policy_tool.py
"""

import os
import sys
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

WORKER_NAME = "policy_tool_worker"


# ─────────────────────────────────────────────
# MCP Client — Sprint 3: Thay bằng real MCP call
# ─────────────────────────────────────────────

def _call_mcp_tool(tool_name: str, tool_input: dict) -> dict:
    """
    Gọi MCP tool.

    Sprint 3 TODO: Implement bằng cách import mcp_server hoặc gọi HTTP.

    Hiện tại: Import trực tiếp từ mcp_server.py (trong-process mock).
    """
    from datetime import datetime

    try:
        # TODO Sprint 3: Thay bằng real MCP client nếu dùng HTTP server
        from mcp_server import dispatch_tool
        result = dispatch_tool(tool_name, tool_input)
        return {
            "tool": tool_name,
            "input": tool_input,
            "output": result,
            "error": None,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "tool": tool_name,
            "input": tool_input,
            "output": None,
            "error": {"code": "MCP_CALL_FAILED", "reason": str(e)},
            "timestamp": datetime.now().isoformat(),
        }


# ─────────────────────────────────────────────
# LLM Policy Analysis Helper
# ─────────────────────────────────────────────

def _call_llm_for_policy(task: str, chunks: list):
    """
    Gọi LLM để phân tích policy phức tạp hơn rule-based.

    Primary:  Anthropic Claude (giống synthesis.py)
    Fallback: OpenAI gpt-4o-mini
    Fallback: None (graceful degradation — caller dùng rule-based only)

    Returns:
        dict with keys: policy_applies, llm_exceptions, explanation, confidence
        OR None nếu LLM không khả dụng
    """
    # Build context from chunks
    context_lines = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk.get("source", "unknown")
        text = chunk.get("text", "")
        context_lines.append(f"[{i}] Nguồn: {source}\n{text}")
    context_text = "\n\n".join(context_lines) if context_lines else "(Không có tài liệu tham khảo)"

    system_prompt = """Bạn là Policy Analyst chuyên về chính sách hoàn tiền và quyền truy cập hệ thống.

    Nhiệm vụ: Phân tích yêu cầu của khách hàng/nhân viên và xác định liệu chính sách có áp dụng không, và có ngoại lệ nào không.

    Các ngoại lệ phổ biến cần phát hiện:
    - Flash Sale: không được hoàn tiền (Điều 3, chính sách v4)
    - Sản phẩm kỹ thuật số (license key, subscription, kỹ thuật số): không được hoàn tiền
    - Sản phẩm đã kích hoạt, đã đăng ký, đã sử dụng: không được hoàn tiền
    - Đơn trước 01/02/2026: áp dụng chính sách v3 (không có trong tài liệu — cần flag)

    Quy tắc nghiêm ngặt:
    1. CHỈ dựa vào context được cung cấp. KHÔNG bịa policy rules.
    2. Trả về JSON hợp lệ theo đúng format yêu cầu.
    3. Nếu không đủ thông tin → policy_applies=true (không chặn mà không có cơ sở).

    Trả về JSON với format sau (không có markdown, không có ```json):
    {
    "policy_applies": true,
    "llm_exceptions": [
        {"type": "tên_exception", "rule": "Câu policy rule cụ thể", "source": "tên_file"}
    ],
    "explanation": "Giải thích ngắn gọn lý do quyết định",
    "confidence": 0.85
    }"""

    user_content = f"""Yêu cầu: {task}

    === TÀI LIỆU CHÍNH SÁCH ===
    {context_text}

    Hãy phân tích và trả về JSON theo format yêu cầu."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    raw_response = None

    # Primary: Anthropic Claude
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        model = os.getenv("LLM_MODEL", "claude-sonnet-4-6")

        system_msg = ""
        user_msgs = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                user_msgs.append(m)

        response = client.messages.create(
            model=model,
            max_tokens=1024,
            temperature=0,
            system=system_msg,
            messages=user_msgs,
        )
        raw_response = response.content[0].text
    except Exception as e:
        print(f"⚠️  [policy_tool] Anthropic failed: {e}")

    # Fallback: OpenAI gpt-4o-mini
    if raw_response is None:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0,
                max_tokens=1024,
            )
            raw_response = response.choices[0].message.content
        except Exception as e:
            print(f"⚠️  [policy_tool] OpenAI fallback failed: {e}")

    # Nếu cả hai LLM fail → graceful degradation
    if raw_response is None:
        return None

    # Parse JSON response
    try:
        import json, re
        cleaned = raw_response.strip()
        # Strip markdown code fences: ```json ... ``` hoặc ``` ... ```
        cleaned = re.sub(r"^```[a-z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()
        result = json.loads(cleaned)
        if "policy_applies" not in result:
            raise ValueError("Missing 'policy_applies' key in LLM response")
        return result
    except Exception as e:
        print(f"⚠️  [policy_tool] JSON parse failed: {e}\nRaw: {raw_response[:200]}")
        return None


# ─────────────────────────────────────────────
# Policy Analysis Logic
# ─────────────────────────────────────────────

def analyze_policy(task: str, chunks: list) -> dict:
    """
    Phân tích policy dựa trên context chunks.

    TODO Sprint 2: Implement logic này với LLM call hoặc rule-based check.

    Cần xử lý các exceptions:
    - Flash Sale → không được hoàn tiền
    - Digital product / license key / subscription → không được hoàn tiền
    - Sản phẩm đã kích hoạt → không được hoàn tiền
    - Đơn hàng trước 01/02/2026 → áp dụng policy v3 (không có trong docs)

    Returns:
        dict with: policy_applies, policy_name, exceptions_found, source, rule, explanation
    """
    task_lower = task.lower()
    context_text = " ".join([c.get("text", "") for c in chunks]).lower()

    # --- Rule-based exception detection ---
    exceptions_found = []

    # Exception 1: Flash Sale
    if "flash sale" in task_lower or "flash sale" in context_text:
        exceptions_found.append({
            "type": "flash_sale_exception",
            "rule": "Đơn hàng Flash Sale không được hoàn tiền (Điều 3, chính sách v4).",
            "source": "policy_refund_v4.txt",
        })

    # Exception 2: Digital product
    if any(kw in task_lower for kw in ["license key", "license", "subscription", "kỹ thuật số"]):
        exceptions_found.append({
            "type": "digital_product_exception",
            "rule": "Sản phẩm kỹ thuật số (license key, subscription) không được hoàn tiền (Điều 3).",
            "source": "policy_refund_v4.txt",
        })

    # Exception 3: Activated product
    if any(kw in task_lower for kw in ["đã kích hoạt", "đã đăng ký", "đã sử dụng"]):
        exceptions_found.append({
            "type": "activated_exception",
            "rule": "Sản phẩm đã kích hoạt hoặc đăng ký tài khoản không được hoàn tiền (Điều 3).",
            "source": "policy_refund_v4.txt",
        })

    # Determine policy_applies
    policy_applies = len(exceptions_found) == 0

    # Determine which policy version applies (temporal scoping)
    # TODO: Check nếu đơn hàng trước 01/02/2026 → v3 applies (không có docs, nên flag cho synthesis)
    policy_name = "refund_policy_v4"
    policy_version_note = ""
    if "31/01" in task_lower or "30/01" in task_lower or "trước 01/02" in task_lower:
        policy_version_note = "Đơn hàng đặt trước 01/02/2026 áp dụng chính sách v3 (không có trong tài liệu hiện tại)."

    # --- LLM second pass (Sprint 2) ---
    llm_result = _call_llm_for_policy(task, chunks)

    if llm_result is not None:
        # Merge LLM exceptions không trùng với rule-based
        existing_types = {ex["type"] for ex in exceptions_found}
        for llm_ex in llm_result.get("llm_exceptions", []):
            if llm_ex.get("type") not in existing_types:
                exceptions_found.append(llm_ex)
                existing_types.add(llm_ex.get("type"))

        # policy_applies=False nếu LLM phát hiện exceptions
        if not llm_result.get("policy_applies", True):
            policy_applies = False

        # Dùng LLM explanation (thay cho string "TODO")
        explanation = llm_result.get("explanation", "Analyzed via rule-based + LLM policy check.")
        llm_confidence = llm_result.get("confidence", None)
    else:
        # LLM không khả dụng → giữ rule-based, không crash
        explanation = "Analyzed via rule-based policy check (LLM unavailable)."
        llm_confidence = None

    # Re-evaluate sau khi merge (source of truth duy nhất là exceptions_found)
    policy_applies = len(exceptions_found) == 0

    sources = list({c.get("source", "unknown") for c in chunks if c})

    result = {
        "policy_applies": policy_applies,
        "policy_name": policy_name,
        "exceptions_found": exceptions_found,
        "source": sources,
        "policy_version_note": policy_version_note,
        "explanation": explanation,
    }
    if llm_confidence is not None:
        result["llm_confidence"] = llm_confidence

    return result


# ─────────────────────────────────────────────
# Worker Entry Point
# ─────────────────────────────────────────────

def run(state: dict) -> dict:
    """
    Worker entry point — gọi từ graph.py.

    Args:
        state: AgentState dict

    Returns:
        Updated AgentState với policy_result và mcp_tools_used
    """
    task = state.get("task", "")
    chunks = state.get("retrieved_chunks", [])
    needs_tool = state.get("needs_tool", False)

    state.setdefault("workers_called", [])
    state.setdefault("history", [])
    state.setdefault("mcp_tools_used", [])

    state["workers_called"].append(WORKER_NAME)

    worker_io = {
        "worker": WORKER_NAME,
        "input": {
            "task": task,
            "chunks_count": len(chunks),
            "needs_tool": needs_tool,
        },
        "output": None,
        "error": None,
    }

    try:
        # Step 1: Nếu chưa có chunks, gọi MCP search_kb
        if not chunks and needs_tool:
            mcp_result = _call_mcp_tool("search_kb", {"query": task, "top_k": 3})
            state["mcp_tools_used"].append(mcp_result)
            state["history"].append(f"[{WORKER_NAME}] called MCP search_kb")

            if mcp_result.get("output") and mcp_result["output"].get("chunks"):
                chunks = mcp_result["output"]["chunks"]
                state["retrieved_chunks"] = chunks

        # Step 2: Phân tích policy
        policy_result = analyze_policy(task, chunks)
        state["policy_result"] = policy_result

        # Step 3: Nếu cần thêm info từ MCP (e.g., ticket status), gọi get_ticket_info
        if needs_tool and any(kw in task.lower() for kw in ["ticket", "p1", "jira"]):
            mcp_result = _call_mcp_tool("get_ticket_info", {"ticket_id": "P1-LATEST"})
            state["mcp_tools_used"].append(mcp_result)
            state["history"].append(f"[{WORKER_NAME}] called MCP get_ticket_info")

        worker_io["output"] = {
            "policy_applies": policy_result["policy_applies"],
            "exceptions_count": len(policy_result.get("exceptions_found", [])),
            "mcp_calls": len(state["mcp_tools_used"]),
        }
        state["history"].append(
            f"[{WORKER_NAME}] policy_applies={policy_result['policy_applies']}, "
            f"exceptions={len(policy_result.get('exceptions_found', []))}"
        )

    except Exception as e:
        worker_io["error"] = {"code": "POLICY_CHECK_FAILED", "reason": str(e)}
        state["policy_result"] = {"error": str(e)}
        state["history"].append(f"[{WORKER_NAME}] ERROR: {e}")

    state.setdefault("worker_io_logs", []).append(worker_io)
    return state


# ─────────────────────────────────────────────
# Test độc lập
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("Policy Tool Worker — Standalone Test")
    print("=" * 50)

    test_cases = [
        {
            "task": "Khách hàng Flash Sale yêu cầu hoàn tiền vì sản phẩm lỗi — được không?",
            "retrieved_chunks": [
                {"text": "Ngoại lệ: Đơn hàng Flash Sale không được hoàn tiền.", "source": "policy_refund_v4.txt", "score": 0.9}
            ],
        },
        {
            "task": "Khách hàng muốn hoàn tiền license key đã kích hoạt.",
            "retrieved_chunks": [
                {"text": "Sản phẩm kỹ thuật số (license key, subscription) không được hoàn tiền.", "source": "policy_refund_v4.txt", "score": 0.88}
            ],
        },
        {
            "task": "Khách hàng yêu cầu hoàn tiền trong 5 ngày, sản phẩm lỗi, chưa kích hoạt.",
            "retrieved_chunks": [
                {"text": "Yêu cầu trong 7 ngày làm việc, sản phẩm lỗi nhà sản xuất, chưa dùng.", "source": "policy_refund_v4.txt", "score": 0.85}
            ],
        },
    ]

    for tc in test_cases:
        print(f"\n▶ Task: {tc['task'][:70]}...")
        result = run(tc.copy())
        pr = result.get("policy_result", {})
        print(f"  policy_applies: {pr.get('policy_applies')}")
        if pr.get("exceptions_found"):
            for ex in pr["exceptions_found"]:
                print(f"  exception: {ex['type']} — {ex['rule'][:60]}...")
        print(f"  MCP calls: {len(result.get('mcp_tools_used', []))}")

    print("\n✅ policy_tool_worker test done.")
