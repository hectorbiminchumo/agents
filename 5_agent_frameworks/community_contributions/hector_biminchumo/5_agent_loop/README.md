# Agent loop template

A Google ADK **orchestrator** agent leads a team of framework workers (AWS Strands, Pydantic AI,
Microsoft Agent Framework, Agno, Mastra). It gives each worker an objective, runs them in
parallel against one shared SQLite board, watches the board fill in live, checks each result and
sends a builder back to fix a broken one (once). 

The loop is generic. What the team builds is defined in two files, `project.py` and `prompts.py`.
The shipped example is the original Week 5 project: a language arcade where each worker invents
one small browser game.

```bash
uv run agent_loop.py --dry-run                 # show the team, call no models
uv run agent_loop.py                           # run with the default topic
uv run agent_loop.py --language French         # the flag name comes from TOPIC_FLAG
uv run agent_loop.py --skip agno mastra        # leave workers out
uv run agent_loop.py --no-open                 # do not open the result at the end
```

A real run calls paid models (OpenAI for the workers, Gemini for the orchestrator) and overwrites
`site/`. Copy `site/` first if you want to keep an earlier result. Mastra needs a one-time
`npm install` inside `workers/mastra/`.

## How a run works

1. `agent_loop.py` discovers the workers (`catalog.py`), then starts the orchestrator.
2. The orchestrator calls its tools in the order `prompts.ORCHESTRATOR_PROMPT` describes:

   `author_style` -> `launch_worker` (once per framework) -> `wait_for_team` -> `test_game` ->
    `relaunch_worker` (only if something is broken) -> `build_hub`.
3. `launch_worker` writes the worker's task onto the board (`prompts.WORKER_TASK`) and starts the

   worker as a subprocess with the task id and the board path. The worker claims that task, plans
    its own steps, writes its files into `site/<framework key>/` and ticks the steps off.
4. Everything is coordinated through the board file `site/board.sqlite`. The workers never talk

   to the orchestrator directly.

## What to change for a new goal

Work through this list from top to bottom.

### 1. `project.py` - the settings (always)

| Setting | What it controls |
| --- | --- |
| `NAME`, `UNIT`, `UNIT_PLURAL` | Words used in printed messages and in the kickoff message. |
| `TOPIC_FLAG`, `TOPIC_DEFAULT`, `TOPIC_HELP` | The one command-line input. It becomes `{topic}` in every prompt. |
| `OUTPUT_FILES` | The files each worker must write into its folder. A deliverable counts as **built** only when all of them exist and are non-empty. |
| `ENTRY_FILE` | The file the QA step opens and the hub page links to. |
| `SHARED_STYLE`, `STYLE_FILE` | Whether to author a shared stylesheet before the workers start. |
| `HUB`, `HUB_FILE`, `HUB_TITLE` | Whether to author a home page linking every deliverable at the end. |
| `QA` | Whether the orchestrator plays each deliverable in a real browser to judge it. |
| `KICKOFF` | The first message the orchestrator receives. |

### 2. `prompts.py` - the text the agents read (always)

Placeholders the code fills in; keep the ones a prompt uses or `format()` will raise `KeyError`.

| Prompt | Read by | Placeholders |
| --- | --- | --- |
| `WORKER_TASK` | each worker, from the board | `{topic}` `{objective}` `{slug}` |
| `FIX_TASK` | a worker sent back to fix its work | `{topic}` `{slug}` `{objective}` `{symptom}` |
| `ORCHESTRATOR_PROMPT` | the orchestrator | `{topic}` `{team}` |
| `STYLE_PROMPT` | the style author | `{topic}` |
| `HUB_PROMPT` | the home-page author | `{topic}` `{links}` |
| `QA_PROMPT` | the browser tester | `{topic}` `{objective}` `{uri}` |

Rules that matter when you rewrite them:

- `WORKER_TASK` must say which files to write (the same names as `OUTPUT_FILES`), that they go
into the folder `"{slug}/"`, and that the worker should read them back before marking done.
- `ORCHESTRATOR_PROMPT` names the tools and their order. If you turn a stage off in `project.py`
(`SHARED_STYLE`, `QA` or `HUB`), delete that step from the prompt too, or the agent will try to
call a tool it does not have.
- The prompts still mention `common.css`, `index.html` and `game.html` by name. If you change
`STYLE_FILE`, `HUB_FILE` or `ENTRY_FILE`, change those words in the prompts as well.
- The orchestrator invents a different objective per worker. Give it example objectives in
`ORCHESTRATOR_PROMPT` for your domain so they come out varied.

### 3. Only if the deliverable is not a web page

- `QA`: `qa_agent.py` drives Chrome through the Playwright MCP server, so it only suits things
that open in a browser. For anything else set `QA = False`, or rewrite `qa_agent.judge_game` to
check your deliverable (it must return `{"works": bool, "note": str}`).
- `SHARED_STYLE` **and** `HUB`: set both to `False` if there is nothing to style or link. The
fallback templates in `css_agent.py` are plain HTML/CSS.
- **Titles**: `finished_games()` reads a `<title>` from the entry file to label each deliverable.
For non-HTML output it falls back to the objective, which is fine.

### 4. Usually leave alone

| File | Why |
| --- | --- |
| `orchestrator.py` | The loop itself: launch, wait, test, relaunch, with the guardrails (80 model calls, 300 s worker timeout, one fix per deliverable). |
| `live_board.py` | Draws the board from the database; it knows nothing about your goal. |
| `board.py`, `workers/board.py`, `workers/mastra/board.ts` | The shared board. All three read `BOARD_PATH`, so they use one file at run time. |
| `workers/*.py`, `workers/mastra/*.ts` | The workers read their task off the board, so the same worker builds any goal. |

### 5. Models and team

- `config.py` sets the orchestrator model and the worker model (or use the `ORCHESTRATOR_MODEL`
and `WORKER_MODEL` environment variables for one run).
- `catalog.py` lists the workers and where each lives. Remove a worker or point one at a different
file there. A worker whose file is missing is simply left out of the team.

## Layout

```
agent_loop.py    entry point and command-line flags
project.py       WHAT the team builds (settings)            <- edit for a new goal
prompts.py       the text each agent reads                  <- edit for a new goal
orchestrator.py  the ADK agent and its tools (the loop)
catalog.py       which workers exist and how to launch them
css_agent.py     writes the shared stylesheet and the home page
qa_agent.py      plays a deliverable in a browser and judges it
live_board.py    the coloured live view of the board
board.py         the shared SQLite board
config.py        model names
workers/         the five workers (Python files plus workers/mastra for TypeScript)
site/            generated output and the shared board file (created on a run)
```

## Checking your changes without spending anything

```bash
uv run agent_loop.py --dry-run
```

This loads `project.py`, discovers the workers and prints the plan, but calls no models. It does
not check your prompts. To check that every placeholder is spelled correctly, format each prompt
once with dummy values in a Python shell before a real run.
