"""Gradio front-end for managing the EngineeringTeam crew end to end:
describe requirements, watch the team build, review the files it produced,
and leave feedback to iterate — without dropping to the terminal.
"""
import contextlib
import queue
import threading
from datetime import datetime

import gradio as gr

import engineering_team.patch  # noqa: F401 — applies CrewAI MCP monkey-patch on import

from .crew import EngineeringTeam
from .main import NO_FEEDBACK_YET, FEEDBACK_LOG, requirements as DEFAULT_REQUIREMENTS
from .tools.sandbox_tools import SANDBOX_DIR, ensure_sandbox, reset_sandbox


class _QueueWriter:
    """A minimal writable stream that pushes text into a queue for live UI updates."""

    def __init__(self, sink: queue.Queue) -> None:
        self._sink = sink

    def write(self, text: str) -> int:
        if text:
            self._sink.put(text)
        return len(text)

    def flush(self) -> None:
        pass


def _run_crew_streaming(build_requirements: str, feedback_text: str):
    """Kick off the crew in a background thread, yielding captured console output live."""
    log_queue: queue.Queue = queue.Queue()
    done = threading.Event()
    error_holder: dict[str, str] = {}

    def _worker() -> None:
        writer = _QueueWriter(log_queue)
        try:
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                ensure_sandbox()
                EngineeringTeam().crew().kickoff(inputs={
                    "requirements": build_requirements,
                    "feedback": feedback_text,
                })
        except Exception as exc:
            error_holder["error"] = str(exc)
        finally:
            done.set()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    buffer = ""
    while not done.is_set() or not log_queue.empty():
        try:
            buffer += log_queue.get(timeout=0.3)
            yield buffer
        except queue.Empty:
            continue

    buffer += f"\n\n❌ Error: {error_holder['error']}" if "error" in error_holder else "\n\n✅ Done."
    yield buffer


def _current_feedback_log() -> str:
    return FEEDBACK_LOG.read_text() if FEEDBACK_LOG.exists() else NO_FEEDBACK_YET


def build_handler(req_text: str):
    req_text = (req_text or "").strip() or DEFAULT_REQUIREMENTS
    yield from _run_crew_streaming(req_text, _current_feedback_log())


def feedback_handler(req_text: str, comment: str):
    comment = (comment or "").strip()
    if not comment:
        yield "⚠️ Enter some feedback before sending."
        return

    ensure_sandbox()
    FEEDBACK_LOG.parent.mkdir(parents=True, exist_ok=True)
    existing = FEEDBACK_LOG.read_text() if FEEDBACK_LOG.exists() else ""
    timestamp = datetime.now().isoformat(timespec="seconds")
    entry = f"## {timestamp}\n{comment}\n"
    FEEDBACK_LOG.write_text(existing + ("\n" if existing else "") + entry)

    req_text = (req_text or "").strip() or DEFAULT_REQUIREMENTS
    yield from _run_crew_streaming(req_text, FEEDBACK_LOG.read_text())


def reset_handler() -> str:
    reset_sandbox()
    if FEEDBACK_LOG.exists():
        FEEDBACK_LOG.unlink()
    return "🗑️ Sandbox and feedback history reset. Head to the Build tab to start fresh."


def _list_sandbox_files() -> list[str]:
    if not SANDBOX_DIR.exists():
        return []
    return sorted(p.name for p in SANDBOX_DIR.iterdir() if p.is_file())


def refresh_files_handler():
    return gr.Dropdown(choices=_list_sandbox_files())


def view_file_handler(filename: str) -> str:
    if not filename:
        return ""
    path = SANDBOX_DIR / filename
    if not path.is_file():
        return f"No such file: {filename}"
    return path.read_text()


with gr.Blocks(title="Engineering Team Studio") as demo:
    gr.Markdown(
        "# 🛠️ Engineering Team Studio\n"
        "Describe what you want built, watch the team work, review the files it produced, "
        "and leave feedback to iterate — all from here."
    )

    requirements_box = gr.Textbox(label="Business Requirements", value=DEFAULT_REQUIREMENTS, lines=10)

    with gr.Tab("Build"):
        gr.Markdown("Edit the requirements above, then build. Re-running reuses any existing work in the sandbox.")
        build_btn = gr.Button("🚀 Build System", variant="primary")
        build_log = gr.Textbox(label="Team Activity Log", lines=20, interactive=False, autoscroll=True, buttons=["copy"])
        build_btn.click(build_handler, inputs=[requirements_box], outputs=[build_log])

    with gr.Tab("Feedback"):
        gr.Markdown("Already built something? Leave feedback below and the team will revise it — without starting over.")
        feedback_box = gr.Textbox(label="Your Feedback", lines=4, placeholder="e.g. Add a dark mode toggle to the gradio app.")
        feedback_btn = gr.Button("📝 Send Feedback & Rebuild", variant="primary")
        feedback_log_view = gr.Textbox(label="Team Activity Log", lines=20, interactive=False, autoscroll=True, buttons=["copy"])
        feedback_btn.click(feedback_handler, inputs=[requirements_box, feedback_box], outputs=[feedback_log_view])

    with gr.Tab("Files"):
        gr.Markdown("Browse what the team has written to the sandbox so far.")
        refresh_files_btn = gr.Button("🔄 Refresh File List")
        file_picker = gr.Dropdown(label="Sandbox File", choices=_list_sandbox_files())
        file_view = gr.Code(label="File Contents", lines=25)
        refresh_files_btn.click(refresh_files_handler, outputs=[file_picker])
        file_picker.change(view_file_handler, inputs=[file_picker], outputs=[file_view])

    with gr.Tab("Danger Zone"):
        gr.Markdown("This wipes the sandbox **and** the feedback history completely. Use only for a genuine fresh start.")
        reset_btn = gr.Button("🗑️ Reset Sandbox", variant="stop")
        reset_status = gr.Markdown()
        reset_btn.click(reset_handler, outputs=[reset_status])


def launch() -> None:
    demo.queue().launch()


if __name__ == "__main__":
    launch()
