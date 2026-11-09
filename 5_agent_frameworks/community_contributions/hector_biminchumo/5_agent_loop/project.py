"""The project definition: everything that says WHAT the team builds.

This is the first file to edit when you give the agent loop a new goal. The loop itself
(launch the workers in parallel, watch the shared board, check the work, send a builder
back once) does not change. The text the agents read lives in prompts.py; the settings
that shape the run live here. See README.md for a checklist.

The example below is the original Week 5 project: a language arcade, where each
framework's worker invents one small browser game.
"""

# --- What the run is called -------------------------------------------------------
NAME = "language arcade"  # used in printed messages and the orchestrator's kickoff message
UNIT = "game"  # one builder's deliverable, singular
UNIT_PLURAL = "games"

# --- The one input you pass on the command line -----------------------------------
# Becomes {topic} in every prompt. With TOPIC_FLAG = "language" you run
# `uv run agent_loop.py --language French`.
TOPIC_FLAG = "language"
TOPIC_DEFAULT = "Spanish"
TOPIC_HELP = "the language to learn"

# --- What a finished deliverable looks like ---------------------------------------
# Each worker writes into its own folder, site/<framework key>/. A deliverable counts
# as built when every file below exists and is non-empty (see orchestrator.is_built).
OUTPUT_FILES = ("game.html", "game.css", "game.js")
ENTRY_FILE = "game.html"  # the file the QA step opens and the hub page links to

# --- Optional stages (turn off what your goal does not need) -----------------------
SHARED_STYLE = True  # author a shared stylesheet before the builders start
STYLE_FILE = "common.css"
HUB = True  # author a home page linking every finished deliverable
HUB_FILE = "index.html"
HUB_TITLE = "Learn {topic}"  # used only by the plain fallback template
QA = True  # play each deliverable in a real browser (Playwright) and judge it

# --- The first message the orchestrator receives ----------------------------------
KICKOFF = (
    f"Design and build the {NAME} with your team: give each builder an objective, get the "
    f"{UNIT_PLURAL} built and working, then assemble the home page."
)
