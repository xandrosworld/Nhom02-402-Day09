"""
app.py — Gradio Chat UI cho Day 09 Multi-Agent System
Chạy: python app.py  |  Mở browser: http://localhost:7860
"""

import gradio as gr
from graph import run_graph

# ─────────────────────────────────────────────
# Helpers — build từng section của trace panel
# ─────────────────────────────────────────────

def _summary(result: dict) -> str:
    if not result:
        return "_Chưa có câu hỏi nào._"
    route    = result.get("supervisor_route", "—")
    conf     = result.get("confidence", 0.0)
    latency  = result.get("latency_ms", "—")
    risk     = result.get("risk_high", False)
    run_id   = result.get("run_id", "—")
    workers  = result.get("workers_called", [])

    badge_route = f"`{route}`"
    badge_risk  = "⚠️ **HIGH RISK**" if risk else "✅ Normal"
    conf_bar    = "█" * int(conf * 10) + "░" * (10 - int(conf * 10))

    return (
        f"**Run:** `{run_id}`\n\n"
        f"| | |\n|--|--|\n"
        f"| **Route** | {badge_route} |\n"
        f"| **Confidence** | {conf_bar} {conf:.0%} |\n"
        f"| **Latency** | `{latency} ms` |\n"
        f"| **Risk** | {badge_risk} |\n"
        f"| **Workers ran** | `{'` → `'.join(workers)}` |\n"
    )


def _routing(result: dict) -> str:
    if not result:
        return "_Chưa có dữ liệu._"
    route   = result.get("supervisor_route", "—")
    reason  = result.get("route_reason", "—")
    hitl    = result.get("hitl_triggered", False)
    needs   = result.get("needs_tool", False)
    workers = result.get("workers_called", [])

    flow = " → ".join(["**Supervisor**"] + [f"**{w}**" for w in workers])

    lines = [
        f"### Luồng thực thi\n{flow}\n",
        f"### Quyết định Supervisor",
        f"| Trường | Giá trị |",
        f"|--------|---------|",
        f"| Route chọn | `{route}` |",
        f"| Lý do | {reason} |",
        f"| Needs tool | {'Yes' if needs else 'No'} |",
        f"| HITL triggered | {'⚠️ Yes' if hitl else 'No'} |",
    ]
    return "\n".join(lines)


def _chunks(result: dict) -> list:
    """Trả về list dicts cho gr.JSON."""
    chunks = result.get("retrieved_chunks", []) if result else []
    if not chunks:
        return [{"status": "Không có chunks nào được retrieve"}]
    return [
        {
            "index": i + 1,
            "source": c.get("source", "unknown"),
            "score": round(c.get("score", 0), 4),
            "text": c.get("text", "")[:300] + ("…" if len(c.get("text", "")) > 300 else ""),
        }
        for i, c in enumerate(chunks)
    ]


def _policy(result: dict) -> str:
    if not result:
        return "_Chưa có dữ liệu._"
    pr = result.get("policy_result", {})
    if not pr:
        return "_Policy worker chưa được gọi trong lần chạy này._"

    applies   = pr.get("policy_applies", None)
    name      = pr.get("policy_name", "—")
    sources   = pr.get("source", [])
    note      = pr.get("policy_version_note", "")
    exps      = pr.get("exceptions_found", [])
    explain   = pr.get("explanation", "—")
    llm_conf  = pr.get("llm_confidence", None)

    verdict = "✅ Policy cho phép" if applies else "❌ Policy từ chối / exception"

    lines = [
        f"### Kết quả: {verdict}\n",
        f"| Trường | Giá trị |",
        f"|--------|---------|",
        f"| Policy name | `{name}` |",
        f"| Sources | {', '.join(f'`{s}`' for s in sources) if sources else '—'} |",
    ]
    if llm_conf is not None:
        lines.append(f"| LLM confidence | `{llm_conf:.0%}` |")
    if note:
        lines.append(f"| Version note | ⚠️ {note} |")

    if exps:
        lines.append("\n### Exceptions phát hiện")
        for ex in exps:
            lines.append(
                f"- **`{ex.get('type')}`** ({ex.get('source', '?')}): "
                f"{ex.get('rule', '')}"
            )
    else:
        lines.append("\n_Không có exceptions._")

    lines += [f"\n### LLM Explanation\n> {explain}"]
    return "\n".join(lines)


def _mcp(result: dict) -> list:
    """Trả về list dicts cho gr.JSON."""
    calls = result.get("mcp_tools_used", []) if result else []
    if not calls:
        return [{"status": "Không có MCP tool nào được gọi"}]
    out = []
    for i, c in enumerate(calls):
        out.append({
            "call": i + 1,
            "tool": c.get("tool"),
            "timestamp": c.get("timestamp"),
            "input": c.get("input"),
            "output": c.get("output"),
            "error": c.get("error"),
        })
    return out


def _steps(result: dict) -> str:
    if not result:
        return "_Chưa có dữ liệu._"
    history = result.get("history", [])
    if not history:
        return "_Không có history steps._"
    lines = ["### Pipeline Steps\n"]
    for i, step in enumerate(history, 1):
        # Color-code by actor
        if step.startswith("[supervisor]"):
            icon = "🧠"
        elif step.startswith("[retrieval"):
            icon = "🔍"
        elif step.startswith("[policy"):
            icon = "📋"
        elif step.startswith("[synthesis"):
            icon = "✍️"
        elif step.startswith("[human_review]"):
            icon = "👤"
        elif step.startswith("[graph]"):
            icon = "⚙️"
        else:
            icon = "•"
        lines.append(f"`{i:02d}` {icon} {step}")
    return "\n\n".join(lines)


# ─────────────────────────────────────────────
# Chat handler — gọi pipeline, trả về tất cả outputs
# ─────────────────────────────────────────────

def chat(message: str, history: list):
    if not message.strip():
        empty = {}
        return history, _summary(empty), _routing(empty), _chunks(empty), _policy(empty), _mcp(empty), _steps(empty)

    result = run_graph(message)
    answer = result.get("final_answer") or "(Không có câu trả lời)"
    history = history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": answer},
    ]

    return (
        history,
        _summary(result),
        _routing(result),
        _chunks(result),
        _policy(result),
        _mcp(result),
        _steps(result),
    )


def clear_all():
    empty = {}
    return [], _summary(empty), _routing(empty), _chunks(empty), _policy(empty), _mcp(empty), _steps(empty)


# ─────────────────────────────────────────────
# Gradio UI
# ─────────────────────────────────────────────

EXAMPLE_QUESTIONS = [
    "SLA xử lý ticket P1 là bao lâu?",
    "Khách hàng Flash Sale yêu cầu hoàn tiền vì sản phẩm lỗi — được không?",
    "Cần cấp quyền Level 3 để khắc phục P1 khẩn cấp. Quy trình là gì?",
    "Nhân viên nghỉ phép năm tối đa được bao nhiêu ngày?",
    "Quy trình xử lý sự cố P1 gồm mấy bước?",
    "Khách hàng muốn hoàn tiền license key đã kích hoạt — có được không?",
]

with gr.Blocks(title="IT Helpdesk Agent — Day 09") as demo:

    gr.Markdown("""
    # IT Helpdesk Agent — Multi-Agent Trace Demo
    **Day 09 Lab** · Nhóm 02 · 402 · Supervisor-Worker Pattern
    """)

    with gr.Row():

        # ── Cột trái: Chat ──────────────────────────────────
        with gr.Column(scale=5):
            chatbot = gr.Chatbot(label="Cuộc trò chuyện", height=460)

            with gr.Row():
                msg_input = gr.Textbox(
                    placeholder="Nhập câu hỏi...",
                    label="",
                    scale=5,
                    container=False,
                )
                submit_btn = gr.Button("Gửi", variant="primary", scale=1)

            gr.Examples(
                examples=EXAMPLE_QUESTIONS,
                inputs=msg_input,
                label="Câu hỏi mẫu",
            )
            clear_btn = gr.Button("Xóa lịch sử", variant="secondary", size="sm")

        # ── Cột phải: Trace Panel ───────────────────────────
        with gr.Column(scale=4):
            gr.Markdown("## Trace Panel")

            summary_md = gr.Markdown(value="_Chưa có câu hỏi nào._")

            with gr.Tabs():

                with gr.Tab("🧠 Routing"):
                    routing_md = gr.Markdown(value="_Chưa có dữ liệu._")

                with gr.Tab("🔍 Chunks"):
                    chunks_json = gr.JSON(
                        value=[{"status": "Chưa có dữ liệu"}],
                        label="Retrieved Chunks",
                    )

                with gr.Tab("📋 Policy"):
                    policy_md = gr.Markdown(value="_Chưa có dữ liệu._")

                with gr.Tab("🔧 MCP Tools"):
                    mcp_json = gr.JSON(
                        value=[{"status": "Chưa có dữ liệu"}],
                        label="MCP Tool Calls",
                    )

                with gr.Tab("⚙️ Pipeline Steps"):
                    steps_md = gr.Markdown(value="_Chưa có dữ liệu._")

    # ── Tất cả outputs ──
    all_outputs = [chatbot, summary_md, routing_md, chunks_json, policy_md, mcp_json, steps_md]

    submit_btn.click(
        fn=chat,
        inputs=[msg_input, chatbot],
        outputs=all_outputs,
    ).then(fn=lambda: "", outputs=msg_input)

    msg_input.submit(
        fn=chat,
        inputs=[msg_input, chatbot],
        outputs=all_outputs,
    ).then(fn=lambda: "", outputs=msg_input)

    clear_btn.click(fn=clear_all, outputs=all_outputs)


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        inbrowser=True,
    )
