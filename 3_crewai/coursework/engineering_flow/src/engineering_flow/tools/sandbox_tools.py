"""Per-team sandbox tools.

Unlike a single global sandbox, this Flow runs several engineering teams at
once, each building a different system in parallel. Every team needs its own
isolated directory so their files don't collide, so the tools here are built
by a factory that closes over a specific sandbox directory instead of being
fixed module-level singletons.
"""
from pathlib import Path
import shutil
import subprocess

from crewai.tools import tool


def _init_uv_project(sandbox_dir: Path) -> None:
    subprocess.run(["uv", "init", "--bare", "--python", "3.13"], cwd=sandbox_dir, check=True)
    subprocess.run(["uv", "add", "gradio"], cwd=sandbox_dir, check=True)


def ensure_sandbox(sandbox_dir: Path) -> None:
    """Initialize a team's sandbox as a uv project with gradio if not already set up.

    Never deletes existing files — safe to call on every run.
    """
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    if (sandbox_dir / "pyproject.toml").exists():
        return
    _init_uv_project(sandbox_dir)


def reset_sandbox(sandbox_dir: Path) -> None:
    """Wipe a single team's sandbox and re-initialize it as a fresh uv project."""
    if sandbox_dir.exists():
        shutil.rmtree(sandbox_dir)
    sandbox_dir.mkdir(parents=True)
    _init_uv_project(sandbox_dir)


def _never_cache(*_args, **_kwargs) -> bool:
    return False


def make_sandbox_tools(sandbox_dir: Path) -> list:
    """Build a fresh set of sandbox tools scoped to `sandbox_dir`.

    Call this once per team/Crew instance so each team's tools read and
    write only within their own directory.
    """
    sandbox_dir = Path(sandbox_dir)
    ensure_sandbox(sandbox_dir)

    @tool("List Sandbox Files")
    def list_sandbox_files() -> str:
        """
        List the filenames currently in this team's sandbox directory.

        Returns:
            A newline-separated list of filenames, or a message if the
            sandbox is empty.
        """
        names = sorted(p.name for p in sandbox_dir.iterdir())
        return "\n".join(names) if names else "The sandbox is empty."

    @tool("Read Sandbox File")
    def read_sandbox_file(filename: str) -> str:
        """
        Read and return the text contents of a file in this team's sandbox directory.

        Args:
            filename: The name of the file to read (e.g. "solution.py").
        Returns:
            The file's contents, or a message if the file does not exist.
        """
        path = sandbox_dir / filename
        if not path.is_file():
            return f"No such file in the sandbox: {filename}"
        return path.read_text()

    @tool("Write Sandbox File")
    def write_sandbox_file(filename: str, content: str) -> str:
        """
        Write text to a file in this team's sandbox directory, replacing any
        existing file with the same name.

        Args:
            filename: The name of the file to write (e.g. "solution.py").
            content: The text content to write.
        Returns:
            A confirmation message.
        """
        path = sandbox_dir / filename
        path.write_text(content)
        return f"Wrote {len(content)} characters to {filename}."

    @tool("Run Sandbox Python File")
    def run_sandbox_python(filename: str) -> str:
        """
        Execute a Python file from this team's sandbox directory inside an
        ephemeral Docker container, with the sandbox mounted as the working
        directory, using `uv run` to run the code in the uv project.

        Returns the exit code, stdout, and stderr, clearly labeled. Note that
        Python's unittest module prints test results — including failures and
        tracebacks — to stderr by default, not stdout, so stderr is just as
        important as stdout for understanding what happened.

        Args:
            filename: The name of the Python file to run (e.g. "solution.py").
        Returns:
            A labeled block containing the exit code, stdout, and stderr.
        """
        try:
            result = subprocess.run(
                [
                    "docker", "run", "--rm",
                    "-v", f"{sandbox_dir}:/workspace",
                    "-w", "/workspace",
                    "ghcr.io/astral-sh/uv:python3.13-bookworm-slim",
                    "uv", "run", filename,
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            return (
                f"Exit code: {result.returncode}\n\n"
                f"--- stdout ---\n{result.stdout or '(empty)'}\n\n"
                f"--- stderr ---\n{result.stderr or '(empty)'}"
            )
        except subprocess.TimeoutExpired as e:
            stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
            return (
                "The script timed out after 300 seconds.\n\n"
                f"--- stdout so far ---\n{stdout or '(empty)'}\n\n"
                f"--- stderr so far ---\n{stderr or '(empty)'}"
            )

    tools = [list_sandbox_files, read_sandbox_file, write_sandbox_file, run_sandbox_python]
    # Sandbox state changes between calls (files appear/change/run), so caching tool
    # results would feed agents stale data. Opt out of CrewAI's default tool caching.
    for t in tools:
        t.cache_function = _never_cache
    return tools
