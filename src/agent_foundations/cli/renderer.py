from rich.console import Console
from rich.panel import Panel

from agent_foundations.runtime.agent import AgentResult


def render_result(console: Console, result: AgentResult) -> None:
    console.print(Panel(result.answer, title="Agent answer"))
    console.print(f"Session: {result.session_id} | Steps: {result.steps}")
