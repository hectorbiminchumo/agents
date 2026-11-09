"""The orchestrator: a Google ADK agent that runs the whole Week 5 team as a loop.

The orchestrator is not a Python loop that calls the workers. It is itself an ADK
agent, given a goal (build what project.py describes with this team) and tools for the
mechanical parts: author the shared look, kick off each framework's builder, wait
for the team, play each finished game in a real browser to check it, and send a
builder back once to fix a game that does not work. The agent owns the decisions;
the tools own the mechanics.

The whole run lives on one event loop. The launch and wait tools spawn workers with
plain subprocess.Popen (no asyncio transports to outlive the loop), and the browser
QA closes its MCP toolset in-loop, so there is no "event loop is closed" teardown.
"""

from __future__ import annotations

import asyncio
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

from quiet import silence

silence()

from google.adk.agents import LlmAgent  # noqa: E402
from google.adk.agents.invocation_context import LlmCallsLimitExceededError  # noqa: E402
from google.adk.agents.run_config import RunConfig  # noqa: E402
from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402
from rich.live import Live  # noqa: E402

import board  # noqa: E402
import catalog  # noqa: E402
import config  # noqa: E402
import css_agent  # noqa: E402
import live_board  # noqa: E402
import project  # noqa: E402
import prompts  # noqa: E402
import qa_agent  # noqa: E402

_APP = "agent_loop"
_MAX_TURNS = 80  # bounds the outer loop so it cannot thrash; the happy path is far fewer
WORKER_TIMEOUT = int(os.environ.get("WORKER_TIMEOUT_S", "300"))  # a worker hung past this is stopped so the run never stalls
QA_TIMEOUT = int(os.environ.get("QA_TIMEOUT_S", "150"))  # a browser QA wedged past this is given up on so the run never stalls
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _read_title(game_html: Path) -> str:
    """The title the builder gave its deliverable, read from its HTML entry file (empty if not found)."""
    try:
        match = _TITLE_RE.search(game_html.read_text(encoding="utf-8"))
    except OSError:
        return ""
    return match.group(1).strip() if match else ""


def is_built(folder: Path) -> bool:
    """True if every file in project.OUTPUT_FILES exists in the folder and is non-empty."""
    return all((folder / f).exists() and (folder / f).stat().st_size for f in project.OUTPUT_FILES)


def _launch(goal_id: int, worker: dict, board_path: Path) -> subprocess.Popen:
    """Start one worker as a subprocess against the shared board.

    stdout and stderr go to DEVNULL: a worker's framework banner would otherwise tear
    the live board, and the worker only ever talks to us through the board. On POSIX,
    start_new_session puts the worker and its uv/npx/MCP tree in their own session so a
    timeout can stop the whole tree at once; on Windows the same job is done by
    taskkill /T in _terminate, so no new group is needed at launch.
    """
    argv = catalog.launch_argv(worker, goal_id, board_path)
    cwd = str((catalog.HERE / worker["file"]).resolve().parent)
    group = {} if sys.platform == "win32" else {"start_new_session": True}
    return subprocess.Popen(
        argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=cwd, **group
    )


def _terminate(proc: subprocess.Popen) -> None:
    """Stop a worker and its uv/npx/MCP child tree (used only when a worker overruns its
    timeout). On Windows taskkill /T kills the whole tree by pid; on POSIX a SIGTERM to
    the process group does the same."""
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, OSError):
        pass


class Team:
    """The orchestrator's working state: the discovered workers and what has been
    launched so far. The tools read and mutate this; the agent never sees it."""

    def __init__(self, topic: str, workers: list[dict], site_dir: Path, board_path: Path) -> None:
        self.topic = topic
        self.workers = workers
        self.site_dir = site_dir
        self.board_path = board_path
        self.by_key = {w["key"]: w for w in workers}
        self.by_slug = {w["slug"]: w for w in workers}
        self.objectives: dict[str, str] = {}  # slug -> the objective the orchestrator assigned
        self.registry: dict[int, dict] = {}  # goal id -> worker (with its objective), colours the live board
        self.pending: list[subprocess.Popen] = []  # launched but not yet waited for
        self.fixed: set[str] = set()  # slugs that have had their one fix

    def _built(self, slug: str) -> bool:
        return is_built(self.site_dir / slug)

    def status(self) -> str:
        lines = []
        for w in self.workers:
            slug = w["slug"]
            objective = self.objectives.get(slug)
            who = f"{w['name']} ({objective})" if objective else w["name"]
            lines.append(f"  {who} [{slug}/]: {'built' if self._built(slug) else 'NOT built'}")
        return "Team status:\n" + "\n".join(lines)

    def finished_games(self) -> list[dict]:
        """The built games as [{label, slug}], each labelled by the title its builder gave it."""
        games = []
        for worker in self.workers:
            slug = worker["slug"]
            if not self._built(slug):
                continue
            label = _read_title(self.site_dir / slug / project.ENTRY_FILE) or self.objectives.get(slug) or worker["name"]
            games.append({"label": label, "slug": slug})
        return games


def make_tools(team: Team) -> list:
    """Build the orchestrator agent's tools as closures over the team state."""

    async def author_style() -> str:
        """Author the shared house style (the stylesheet every deliverable links). Do
        this once, before the builders start."""
        await css_agent.author_style(team.topic, team.site_dir)
        return f"Authored {project.STYLE_FILE}, the shared house style."

    def launch_worker(framework: str, objective: str) -> str:
        """Start one framework's builder, giving it an objective to build a deliverable
        for. The builder designs the deliverable itself. Returns immediately; it works in
        the background. Start all your builders, then call wait_for_team.

        Args:
            framework: the framework key, one of strands, pydantic, maf, agno, mastra.
            objective: the objective this builder's deliverable covers. Give each
                builder a different one.
        """
        worker = team.by_key.get(framework)
        if worker is None:
            return f"No builder named '{framework}'. Your team is: {', '.join(team.by_key)}."
        slug = worker["slug"]
        if slug in team.objectives:
            return f"{worker['name']} is already building a game on {team.objectives[slug]}."
        team.objectives[slug] = objective
        (team.site_dir / slug).mkdir(parents=True, exist_ok=True)
        task = prompts.WORKER_TASK.format(topic=team.topic, objective=objective, slug=slug)
        goal_id = board.add_goal(task)
        team.registry[goal_id] = {**worker, "objective": objective}
        team.pending.append(_launch(goal_id, worker, team.board_path))
        return f"Launched {worker['name']} to build a {project.UNIT} on {team.topic}: {objective} (folder {slug}/)."

    async def wait_for_team() -> str:
        """Wait until every builder you have started has finished, watching the shared
        board fill in while they work. Returns which deliverables are now built."""
        procs = team.pending
        team.pending = []
        if not procs:
            return team.status()
        started = time.monotonic()
        stopped = False
        with Live(live_board.render(team.registry), console=live_board.console, refresh_per_second=8) as live:
            while any(p.poll() is None for p in procs):
                live.update(live_board.render(team.registry))
                if not stopped and time.monotonic() - started > WORKER_TIMEOUT:
                    for p in procs:
                        if p.poll() is None:
                            _terminate(p)
                    stopped = True
                await asyncio.sleep(0.15)
            live.update(live_board.render(team.registry))
        return team.status()

    async def test_game(slug: str) -> str:
        """Open one finished deliverable in a real browser and play it to judge whether
        it works. Watch the browser to see it being checked.

        Args:
            slug: the builder's folder name, which is its framework key, e.g. strands.
        """
        worker = team.by_slug.get(slug)
        if worker is None:
            return f"No game in folder '{slug}'. Folders: {', '.join(team.by_slug)}."
        if not team._built(slug):
            missing = [f for f in project.OUTPUT_FILES if not (team.site_dir / slug / f).exists() or not (team.site_dir / slug / f).stat().st_size]
            return f"{slug} is not built yet (missing or empty: {', '.join(missing)}). Wait for the team, or fix it."
        uri = (team.site_dir / slug / project.ENTRY_FILE).resolve().as_uri()
        live_board.console.print(f"Playing {worker['name']}'s game to check it", style=worker["colour"])
        try:
            verdict = await asyncio.wait_for(
                qa_agent.judge_game(team.topic, team.objectives.get(slug, ""), uri),
                timeout=QA_TIMEOUT,
            )
        except Exception as exc:
            live_board.console.print(f"  could not finish checking {worker['name']} ({type(exc).__name__})", style="dim")
            return f"Could not finish checking {slug} ({type(exc).__name__}); leave it as built."
        if not verdict:
            live_board.console.print(f"  could not play {worker['name']} (browser unavailable)", style="dim")
            return f"Could not play {slug} (the browser may be unavailable); leave it as built."
        works = bool(verdict.get("works"))
        note = verdict.get("note", "")
        live_board.console.print(f"  {worker['name']}: {'WORKS' if works else 'BROKEN'}. {note}", style="green" if works else "red")
        return f"{slug}: {'WORKS' if works else 'BROKEN'}. {note}"

    def relaunch_worker(framework: str, problem: str) -> str:
        """Send a framework's builder back to fix its deliverable, once. Returns immediately;
        call wait_for_team afterwards. Each game gets at most one fix attempt.

        Args:
            framework: the framework key whose game is broken.
            problem: one short sentence describing what is broken.
        """
        worker = team.by_key.get(framework)
        if worker is None:
            return f"No builder named '{framework}'."
        slug = worker["slug"]
        if slug in team.fixed:
            return f"{worker['name']} has already had its one fix; leaving its game as is."
        team.fixed.add(slug)
        objective = team.objectives.get(slug, "")
        text = prompts.FIX_TASK.format(topic=team.topic, slug=slug, objective=objective, symptom=problem)
        goal_id = board.add_goal(text)
        team.registry[goal_id] = {**worker, "objective": objective}
        team.pending.append(_launch(goal_id, worker, team.board_path))
        return f"Sent {worker['name']} back to fix its game (folder {slug}/)."

    async def build_hub() -> str:
        """Author the themed home page linking every finished deliverable. Call this
        once, after they are built and checked."""
        games = team.finished_games()
        if not games:
            return "No finished games to link yet; build some first."
        await css_agent.build_hub(team.topic, games, team.site_dir)
        return f"Authored {project.HUB_FILE} linking {len(games)} {project.UNIT}(s): {', '.join(g['label'] for g in games)}."

    tools = [launch_worker, wait_for_team, relaunch_worker]
    if project.SHARED_STYLE:
        tools.insert(0, author_style)
    if project.QA:
        tools.insert(tools.index(relaunch_worker), test_game)
    if project.HUB:
        tools.append(build_hub)
    return tools


def _build_agent(team: Team) -> LlmAgent:
    team_lines = "\n".join(
        f"- {w['name']} (framework key: {w['key']}, folder: {w['slug']}/)"
        for w in team.workers
    )
    instruction = prompts.ORCHESTRATOR_PROMPT.format(topic=team.topic, team=team_lines)
    return LlmAgent(name="orchestrator", model=config.ORCHESTRATOR_MODEL, instruction=instruction, tools=make_tools(team))


async def _run(team: Team) -> None:
    runner = InMemoryRunner(agent=_build_agent(team), app_name=_APP)
    try:
        session = await runner.session_service.create_session(app_name=_APP, user_id="orchestrator")
        async for event in runner.run_async(
            user_id="orchestrator",
            session_id=session.id,
            new_message=types.UserContent(project.KICKOFF),
            run_config=RunConfig(max_llm_calls=_MAX_TURNS),
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text and part.text.strip():
                        live_board.console.print(part.text.strip(), style="dim italic")
    except LlmCallsLimitExceededError:
        # The orchestrator used its whole turn budget. Stop cleanly and let the safety
        # net below finish the site; the games it did build are still on disk.
        print(f"\n  NOTE: the orchestrator reached its {_MAX_TURNS}-step budget; wrapping up with what is built.")
    except Exception as exc:
        # A transient model or network error (a DNS blip, a 5xx from the API) on the
        # orchestrator's own call would otherwise crash the whole run with a traceback.
        # The games are already built on disk, so stop cleanly and let the safety net
        # below finish the hub. The type is printed so a real fault is still visible.
        print(f"\n  NOTE: the orchestrator stopped early after an error ({type(exc).__name__}); wrapping up with what is built.")
    finally:
        try:
            await runner.close()
        except Exception:
            pass


def _ensure_site(team: Team) -> None:
    """A non-LLM safety net so the site always has a look and a front door, even if the
    orchestrator stopped before authoring them. Only fills in what is missing."""
    if project.SHARED_STYLE and not (team.site_dir / project.STYLE_FILE).exists():
        css_agent.write_template_style(team.site_dir)
    if project.HUB and not (team.site_dir / project.HUB_FILE).exists():
        css_agent.write_template_hub(team.topic, team.finished_games(), team.site_dir)
        print(f"  NOTE: the orchestrator did not author {project.HUB_FILE}; wrote the plain template instead.")


def run(topic: str, workers: list[dict], site_dir: Path, board_path: Path) -> Team:
    """Reset the shared board, then let the orchestrator agent build and check the work (see project.py)."""
    site_dir.mkdir(parents=True, exist_ok=True)
    board.reset_board()
    team = Team(topic, workers, site_dir, board_path)
    asyncio.run(_run(team))
    _ensure_site(team)
    return team
