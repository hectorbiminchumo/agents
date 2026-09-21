# Engineering Flow

A CrewAI **Flow** that coordinates several independent engineering teams at once — one hierarchical crew per system/requirement set, each building in its own isolated sandbox, in parallel.

This is a separate, standalone project from `../engineering_team` (which builds one system at a time). It demonstrates the higher-level "Flow over Crews" coordination pattern: instead of one team working through a fixed list of tasks, the Flow spins up N teams — each with its own `engineering_lead` manager and `backend_engineer` / `frontend_engineer` / `test_engineer` — and runs them concurrently against different requirements.

## Installation

Ensure you have Python >=3.10 <3.14 installed. This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
pip install uv
crewai install
```

Add your `OPENAI_API_KEY` to `.env`.

## Running the Project

```bash
crewai run
```

By default this builds two unrelated systems in parallel (see `DEFAULT_SYSTEMS` in `src/engineering_flow/main.py`):

- `trading_account` — a trading simulation account management backend + gradio UI
- `task_tracker` — a personal task tracker backend + gradio UI

Each team's output lands in its own directory: `runs/<system_name>/sandbox/`.

To build different systems, edit `DEFAULT_SYSTEMS` in `main.py` (or pass `systems=[...]` via `EngineeringFlow().kickoff(inputs={...})`) — add as many `SystemSpec(name=..., requirements=...)` entries as you want; each one gets its own team and sandbox.

## How It Works

- `src/engineering_flow/main.py` — the `EngineeringFlow`: prepares the list of systems to build, then fans out a `ThreadPoolExecutor` to run one `EngineeringCrew` per system concurrently, and reports a summary at the end.
- `src/engineering_flow/crews/engineering_crew/` — the reusable per-team crew (hierarchical process, same pattern as `../engineering_team`'s task-1 design): an `engineering_lead` manager delegates design/code/frontend/test work to its 3 engineers.
- `src/engineering_flow/tools/sandbox_tools.py` — sandbox tools built by a **factory** (`make_sandbox_tools(sandbox_dir)`) rather than fixed module-level singletons, so each team's tools read/write only within their own directory and never collide with another team running at the same time.

## Support

- [CrewAI documentation](https://docs.crewai.com)
- [CrewAI GitHub](https://github.com/crewAIInc/crewAI)
