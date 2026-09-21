#!/usr/bin/env python
"""Top-level coordination Flow that manages several independent engineering
teams at once — one team per system/requirement set — each building in its
own isolated sandbox, in parallel.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pydantic import BaseModel, Field

from crewai.flow import Flow, listen, start

from engineering_flow.crews.engineering_crew.engineering_crew import EngineeringCrew

RUNS_DIR = Path(__file__).resolve().parents[2] / "runs"


class SystemSpec(BaseModel):
    name: str
    requirements: str


class TeamResult(BaseModel):
    name: str
    status: str  # "success" | "error"
    summary: str


class EngineeringFlowState(BaseModel):
    systems: list[SystemSpec] = Field(default_factory=list)
    results: list[TeamResult] = Field(default_factory=list)


TRADING_ACCOUNT_REQUIREMENTS = """
A simple account management system for a trading simulation platform.
The system should allow users to create an account, deposit funds, and withdraw funds.
The system should allow users to record that they have bought or sold shares, providing a quantity.
The system should calculate the total value of the user's portfolio, and the profit or loss from the initial deposit.
The system should be able to report the holdings of the user at any point in time.
The system should prevent the user from withdrawing funds that would leave them with a negative balance, or
 from buying more shares than they can afford, or selling shares that they don't have.
 The system has access to a function get_share_price(symbol) which returns the current price of a share, and
 includes a test implementation that returns fixed prices for AAPL, TSLA, GOOGL.
"""

TASK_TRACKER_REQUIREMENTS = """
A simple personal task tracker.
The system should allow a user to create a task with a title, an optional due date, and a priority (low/medium/high).
The system should allow marking a task complete, editing a task's fields, and deleting a task.
The system should be able to list all tasks, optionally filtered by completion status or priority.
The system should be able to report how many tasks are overdue (due date in the past and not complete).
The system should prevent creating a task with an empty title, or editing/deleting a task that doesn't exist.
"""

# Two unrelated systems, each built by its own team, in parallel — a stand-in
# for "several parts of a larger system" or simply several separate products.
DEFAULT_SYSTEMS = [
    SystemSpec(name="trading_account", requirements=TRADING_ACCOUNT_REQUIREMENTS),
    SystemSpec(name="task_tracker", requirements=TASK_TRACKER_REQUIREMENTS),
]


class EngineeringFlow(Flow[EngineeringFlowState]):

    @start()
    def prepare_teams(self):
        if not self.state.systems:
            self.state.systems = DEFAULT_SYSTEMS
        names = ", ".join(s.name for s in self.state.systems)
        print(f"Coordinating {len(self.state.systems)} team(s) in parallel: {names}")

    @listen(prepare_teams)
    def build_systems_in_parallel(self):
        def _build(spec: SystemSpec) -> TeamResult:
            sandbox_dir = RUNS_DIR / spec.name / "sandbox"
            try:
                EngineeringCrew(sandbox_dir=sandbox_dir).crew().kickoff(inputs={
                    "system_name": spec.name,
                    "requirements": spec.requirements,
                })
                return TeamResult(name=spec.name, status="success", summary=f"Built in {sandbox_dir}")
            except Exception as exc:
                return TeamResult(name=spec.name, status="error", summary=str(exc))

        with ThreadPoolExecutor(max_workers=len(self.state.systems)) as pool:
            self.state.results = list(pool.map(_build, self.state.systems))

    @listen(build_systems_in_parallel)
    def report(self):
        print("\n=== Engineering Flow Summary ===")
        for result in self.state.results:
            icon = "✅" if result.status == "success" else "❌"
            print(f"{icon} {result.name}: {result.summary}")


def kickoff():
    EngineeringFlow().kickoff()


def plot():
    EngineeringFlow().plot()


if __name__ == "__main__":
    kickoff()
