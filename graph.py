"""
graph.py — Supervisor Orchestrator
Sprint 1: Implement AgentState, supervisor_node, route_decision và kết nối graph.

Kiến trúc:
    Input → Supervisor → [retrieval_worker | policy_tool_worker | human_review] → synthesis → Output

Chạy thử:
    python graph.py
"""

import json
import os
from datetime import datetime
from typing import TypedDict, Literal, Optional

# Uncomment nếu dùng LangGraph:
# from langgraph.graph import StateGraph, END

# ─────────────────────────────────────────────
# 1. Shared State — dữ liệu đi xuyên toàn graph
# ─────────────────────────────────────────────

class AgentState(TypedDict):
    # Input
    task: str                           # Câu hỏi đầu vào từ user

    # Supervisor decisions
    route_reason: str                   # Lý do route sang worker nào
    risk_high: bool                     # True → cần HITL hoặc human_review
    needs_tool: bool                    # True → cần gọi external tool qua MCP
    hitl_triggered: bool                # True → đã pause cho human review

    # Worker outputs
    retrieved_chunks: list              # Output từ retrieval_worker
    retrieved_sources: list             # Danh sách nguồn tài liệu
    policy_result: dict                 # Output từ policy_tool_worker
    mcp_tools_used: list                # Danh sách MCP tools đã gọi

    # Final output
    final_answer: str                   # Câu trả lời tổng hợp
    sources: list                       # Sources được cite
    confidence: float                   # Mức độ tin cậy (0.0 - 1.0)

    # Trace & history
    history: list                       # Lịch sử các bước đã qua
    workers_called: list                # Danh sách workers đã được gọi
    supervisor_route: str               # Worker được chọn bởi supervisor
    latency_ms: Optional[int]           # Thời gian xử lý (ms)
    run_id: str                         # ID của run này


def make_initial_state(task: str) -> AgentState:
    """Khởi tạo state cho một run mới."""
    return {
        "task": task,
        "route_reason": "",
        "risk_high": False,
        "needs_tool": False,
        "hitl_triggered": False,
        "retrieved_chunks": [],
        "retrieved_sources": [],
        "policy_result": {},
        "mcp_tools_used": [],
        "final_answer": "",
        "sources": [],
        "confidence": 0.0,
        "history": [],
        "workers_called": [],
        "supervisor_route": "",
        "latency_ms": None,
        "run_id": f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    }


# ─────────────────────────────────────────────
# 2. Supervisor Node — quyết định route
# ─────────────────────────────────────────────

def supervisor_node(state: AgentState) -> AgentState:
    """
    Supervisor phân tích task và quyết định route.
    Route reason phải CỤ THỂ — ghi rõ keyword nào trigger, tại sao. [MTT]
    """
    import re as _re
    task = state["task"]
    task_lower = task.lower()
    state["history"].append(f"[supervisor] received task: {task[:80]}")

    route = "retrieval_worker"
    route_reason = ""
    needs_tool = False
    risk_high = False

    # ── Policy / Access keywords → policy_tool_worker ──
    POLICY_RULES = [
        (["hoàn tiền", "refund", "hoàn lại"],          "refund policy question"),
        (["flash sale", "khuyến mãi"],                  "Flash Sale exception case"),
        (["license key", "license", "sản phẩm kỹ thuật số", "digital"], "digital product policy"),
        (["store credit"],                               "store credit policy"),
        (["cấp quyền", "access level", "level 1", "level 2", "level 3",
          "quyền truy cập", "elevated access", "admin access"],  "access control policy"),
        (["contractor", "third-party"],                  "third-party access policy"),
    ]
    triggered_policy = []
    for keywords, reason in POLICY_RULES:
        matched = [kw for kw in keywords if kw in task_lower]
        if matched:
            triggered_policy.append(f"'{matched[0]}' ({reason})")

    # ── SLA / Incident / HR keywords → retrieval_worker ──
    RETRIEVAL_RULES = [
        (["sla", "service level"],         "SLA policy lookup"),
        (["ticket p1", " p1", "sự cố"],   "P1 incident procedure"),
        (["escalat"],                       "escalation procedure"),
        (["on-call", "pagerduty"],          "incident notification"),
        (["quy trình xử lý"],              "procedure lookup"),
        (["remote", "probation"],           "HR policy lookup"),
        (["tài khoản bị khóa", "đăng nhập sai"], "IT helpdesk lookup"),
        (["bao lâu", "bao nhiêu ngày"],    "duration/SLA fact lookup"),
        (["bao nhiêu lần"],                "threshold fact lookup"),
    ]
    triggered_retrieval = []
    for keywords, reason in RETRIEVAL_RULES:
        matched = [kw for kw in keywords if kw in task_lower]
        if matched:
            triggered_retrieval.append(f"'{matched[0]}' ({reason})")

    # ── Risk detection ──
    risk_kws = ["khẩn cấp", "emergency", "urgent", "2am", "3am"]
    if any(kw in task_lower for kw in risk_kws):
        risk_high = True

    # ── Unknown error code → human_review ──
    has_unknown_err = bool(_re.search(r"err-[0-9a-z\-]+", task_lower))

    # ── Decision ──
    if has_unknown_err and not triggered_retrieval:
        route = "human_review"
        route_reason = (f"unknown error code pattern (ERR-xxx) with no matching SLA/procedure keyword "
                        f"→ insufficient context, escalate to human review")

    elif triggered_policy and triggered_retrieval:
        route = "policy_tool_worker"
        needs_tool = True
        route_reason = (f"multi-hop: policy=[{'; '.join(triggered_policy)}] "
                        f"AND retrieval=[{'; '.join(triggered_retrieval)}] "
                        f"→ policy_tool first, retrieval second for cross-document reasoning")

    elif triggered_policy:
        route = "policy_tool_worker"
        needs_tool = True
        route_reason = f"policy/access keywords: {'; '.join(triggered_policy)}"

    elif triggered_retrieval:
        route = "retrieval_worker"
        route_reason = f"SLA/procedure keywords: {'; '.join(triggered_retrieval)}"

    else:
        route = "retrieval_worker"
        route_reason = f"no specific policy or error keyword → default retrieval for general lookup"

    if risk_high:
        route_reason += " | risk_high=True (emergency/urgent context)"

    state["supervisor_route"] = route
    state["route_reason"] = route_reason
    state["needs_tool"] = needs_tool
    state["risk_high"] = risk_high
    state["history"].append(f"[supervisor] route={route} | reason={route_reason}")

    return state


# ─────────────────────────────────────────────
# 3. Route Decision — conditional edge
# ─────────────────────────────────────────────

def route_decision(state: AgentState) -> Literal["retrieval_worker", "policy_tool_worker", "human_review"]:
    """
    Trả về tên worker tiếp theo dựa vào supervisor_route trong state.
    Đây là conditional edge của graph.
    """
    route = state.get("supervisor_route", "retrieval_worker")
    return route  # type: ignore


# ─────────────────────────────────────────────
# 4. Human Review Node — HITL placeholder
# ─────────────────────────────────────────────

def human_review_node(state: AgentState) -> AgentState:
    """
    HITL node: pause và chờ human approval.
    Trong lab này, implement dưới dạng placeholder (in ra warning).

    TODO Sprint 3 (optional): Implement actual HITL với interrupt_before hoặc
    breakpoint nếu dùng LangGraph.
    """
    state["hitl_triggered"] = True
    state["history"].append("[human_review] HITL triggered — awaiting human input")
    state["workers_called"].append("human_review")

    # Placeholder: tự động approve để pipeline tiếp tục
    print(f"\n⚠️  HITL TRIGGERED")
    print(f"   Task: {state['task']}")
    print(f"   Reason: {state['route_reason']}")
    print(f"   Action: Auto-approving in lab mode (set hitl_triggered=True)\n")

    # Sau khi human approve, route về retrieval để lấy evidence
    state["supervisor_route"] = "retrieval_worker"
    state["route_reason"] += " | human approved → retrieval"

    return state


# ─────────────────────────────────────────────
# 5. Import Workers
# ─────────────────────────────────────────────

# Workers — kế thừa từ Day 08, đã config VoyageAI + Anthropic
from workers.retrieval import run as retrieval_run
from workers.policy_tool import run as policy_tool_run
from workers.synthesis import run as synthesis_run


def retrieval_worker_node(state: AgentState) -> AgentState:
    """Wrapper gọi retrieval worker."""
    return retrieval_run(state)


def policy_tool_worker_node(state: AgentState) -> AgentState:
    """Wrapper gọi policy/tool worker."""
    return policy_tool_run(state)


def synthesis_worker_node(state: AgentState) -> AgentState:
    """Wrapper gọi synthesis worker."""
    return synthesis_run(state)


# ─────────────────────────────────────────────
# 6. Build Graph
# ─────────────────────────────────────────────

def build_graph():
    """
    Xây dựng graph với supervisor-worker pattern.

    Option A (đơn giản — Python thuần): Dùng if/else, không cần LangGraph.
    Option B (nâng cao): Dùng LangGraph StateGraph với conditional edges.

    Lab này implement Option A theo mặc định.
    TODO Sprint 1: Có thể chuyển sang LangGraph nếu muốn.
    """
    # Option A: Simple Python orchestrator
    def run(state: AgentState) -> AgentState:
        import time
        start = time.time()

        # Step 1: Supervisor decides route
        state = supervisor_node(state)

        # Step 2: Route to appropriate worker
        route = route_decision(state)

        if route == "human_review":
            state = human_review_node(state)
            # After human approval, continue with retrieval
            state = retrieval_worker_node(state)
        elif route == "policy_tool_worker":
            state = policy_tool_worker_node(state)
            # Policy worker may need retrieval context first
            if not state["retrieved_chunks"]:
                state = retrieval_worker_node(state)
        else:
            # Default: retrieval_worker
            state = retrieval_worker_node(state)

        # Step 3: Always synthesize
        state = synthesis_worker_node(state)

        state["latency_ms"] = int((time.time() - start) * 1000)
        state["history"].append(f"[graph] completed in {state['latency_ms']}ms")
        return state

    return run


# ─────────────────────────────────────────────
# 7. Public API
# ─────────────────────────────────────────────

_graph = build_graph()


def run_graph(task: str) -> AgentState:
    """
    Entry point: nhận câu hỏi, trả về AgentState với full trace.

    Args:
        task: Câu hỏi từ user

    Returns:
        AgentState với final_answer, trace, routing info, v.v.
    """
    state = make_initial_state(task)
    result = _graph(state)
    return result


def save_trace(state: AgentState, output_dir: str = "./artifacts/traces") -> str:
    """Lưu trace ra file JSON."""
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{output_dir}/{state['run_id']}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return filename


# ─────────────────────────────────────────────
# 8. Manual Test
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Day 09 Lab — Supervisor-Worker Graph")
    print("=" * 60)

    test_queries = [
        "SLA xử lý ticket P1 là bao lâu?",
        "Khách hàng Flash Sale yêu cầu hoàn tiền vì sản phẩm lỗi — được không?",
        "Cần cấp quyền Level 3 để khắc phục P1 khẩn cấp. Quy trình là gì?",
    ]

    for query in test_queries:
        print(f"\n▶ Query: {query}")
        result = run_graph(query)
        print(f"  Route   : {result['supervisor_route']}")
        print(f"  Reason  : {result['route_reason']}")
        print(f"  Workers : {result['workers_called']}")
        print(f"  Answer  : {result['final_answer'][:100]}...")
        print(f"  Confidence: {result['confidence']}")
        print(f"  Latency : {result['latency_ms']}ms")

        # Lưu trace
        trace_file = save_trace(result)
        print(f"  Trace saved → {trace_file}")

    print("\n✅ graph.py test complete. Implement TODO sections in Sprint 1 & 2.")
