#!/usr/bin/env python
import sys
import warnings

from datetime import datetime
from pathlib import Path

import engineering_team.patch # noqa: F401 — applies CrewAI MCP monkey-patch on import

from .tools.sandbox_tools import reset_sandbox, ensure_sandbox

from engineering_team.crew import EngineeringTeam

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

# This main file is intended to be a way for you to run your
# crew locally, so refrain from adding unnecessary logic into this file.
# Replace with inputs you want to test with, it will automatically
# interpolate any tasks and agents information

requirements = """
A simple account management system for a trading simulation platform.
The system should allow users to create an account, deposit funds, and withdraw funds.
The system should allow users to record that they have bought or sold shares, providing a quantity.
The system should calculate the total value of the user's portfolio, and the profit or loss from the initial deposit.
The system should be able to report the holdings of the user at any point in time.
The system should be able to report the profit or loss of the user at any point in time.
The system should be able to list the transactions that the user has made over time.
The system should prevent the user from withdrawing funds that would leave them with a negative balance, or
 from buying more shares than they can afford, or selling shares that they don't have.
 The system has access to a function get_share_price(symbol) which returns the current price of a share, and includes a test implementation that returns fixed prices for AAPL, TSLA, GOOGL.
"""

NO_FEEDBACK_YET = "No feedback yet — this is the first build, just implement the requirements."

FEEDBACK_LOG = Path(__file__).resolve().parents[2] / "sandbox" / "feedback_log.md"


def run():
    """
    Run the crew. Reuses the existing sandbox if one is already there, so
    re-running does not throw away prior work — only `reset` does that.
    """
    inputs = {
        'requirements': requirements,
        'feedback': FEEDBACK_LOG.read_text() if FEEDBACK_LOG.exists() else NO_FEEDBACK_YET,
    }

    try:
        ensure_sandbox()
        EngineeringTeam().crew().kickoff(inputs=inputs)
    except Exception as e:
        raise Exception(f"An error occurred while running the crew: {e}")


def reset():
    """
    Wipe the sandbox and the feedback history for a completely fresh start.
    """
    reset_sandbox()
    if FEEDBACK_LOG.exists():
        FEEDBACK_LOG.unlink()
    print("Sandbox and feedback history reset. Run `crewai run` to build from scratch.")


def feedback():
    """
    Give the team feedback on the current deliverable without wiping the sandbox.
    Usage: uv run feedback "your comments here" (or run with no argument to be prompted).
    Feedback accumulates in sandbox/feedback_log.md across rounds, like an ongoing review thread.
    """
    text = sys.argv[1] if len(sys.argv) > 1 else input("Enter your feedback: ")
    text = text.strip()
    if not text:
        print("No feedback provided.")
        return

    ensure_sandbox()
    FEEDBACK_LOG.parent.mkdir(parents=True, exist_ok=True)
    existing = FEEDBACK_LOG.read_text() if FEEDBACK_LOG.exists() else ""
    timestamp = datetime.now().isoformat(timespec="seconds")
    entry = f"## {timestamp}\n{text}\n"
    FEEDBACK_LOG.write_text(existing + ("\n" if existing else "") + entry)

    inputs = {
        'requirements': requirements,
        'feedback': FEEDBACK_LOG.read_text(),
    }

    try:
        EngineeringTeam().crew().kickoff(inputs=inputs)
    except Exception as e:
        raise Exception(f"An error occurred while applying feedback: {e}")


def train():
    """
    Train the crew for a given number of iterations.
    """
    inputs = {
        "topic": "AI LLMs",
        'current_year': str(datetime.now().year)
    }
    try:
        EngineeringTeam().crew().train(n_iterations=int(sys.argv[1]), filename=sys.argv[2], inputs=inputs)

    except Exception as e:
        raise Exception(f"An error occurred while training the crew: {e}")

def replay():
    """
    Replay the crew execution from a specific task.
    """
    try:
        EngineeringTeam().crew().replay(task_id=sys.argv[1])

    except Exception as e:
        raise Exception(f"An error occurred while replaying the crew: {e}")

def test():
    """
    Test the crew execution and returns the results.
    """
    inputs = {
        "topic": "AI LLMs",
        "current_year": str(datetime.now().year)
    }

    try:
        EngineeringTeam().crew().test(n_iterations=int(sys.argv[1]), eval_llm=sys.argv[2], inputs=inputs)

    except Exception as e:
        raise Exception(f"An error occurred while testing the crew: {e}")

def run_with_trigger():
    """
    Run the crew with trigger payload.
    """
    import json

    if len(sys.argv) < 2:
        raise Exception("No trigger payload provided. Please provide JSON payload as argument.")

    try:
        trigger_payload = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        raise Exception("Invalid JSON payload provided as argument")

    inputs = {
        "crewai_trigger_payload": trigger_payload,
        "topic": "",
        "current_year": ""
    }

    try:
        result = EngineeringTeam().crew().kickoff(inputs=inputs)
        return result
    except Exception as e:
        raise Exception(f"An error occurred while running the crew with trigger: {e}")
