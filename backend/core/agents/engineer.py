import asyncio
import shlex
from github import Github
from core.llm_client import llm_complete
from config import GITHUB_TOKEN

github_client = Github(GITHUB_TOKEN) if GITHUB_TOKEN else None

# ─── Allowed shell commands ───────────────────────────────────────────────────

ALLOWED_COMMANDS = [
    "ls", "pwd", "echo", "cat", "grep", "find",
    "git", "python", "node", "npm",
]

BLOCKED = ["rm -rf", "sudo", "chmod 777", "dd if", "> /dev/"]
SHELL_METACHARS = {";", "&", "|", ">", "<", "`", "$", "(", ")", "\n"}
SAFE_GIT_SUBCOMMANDS = {
    "status", "log", "show", "diff", "branch", "remote", "rev-parse",
}
SAFE_VERSION_FLAGS = {"--version", "-v", "version"}


def is_safe(command: str) -> bool:
    cmd = command.strip().lower()
    if any(b in cmd for b in BLOCKED):
        return False
    if any(char in command for char in SHELL_METACHARS):
        return False

    try:
        parts = shlex.split(command)
    except ValueError:
        return False

    if not parts:
        return False

    base = parts[0]
    if base not in ALLOWED_COMMANDS:
        return False

    if base == "find" and any(arg in {"-exec", "-delete"} for arg in parts[1:]):
        return False

    if base == "git":
        return len(parts) > 1 and parts[1] in SAFE_GIT_SUBCOMMANDS

    if base in {"python", "node", "npm"}:
        return len(parts) > 1 and parts[1] in SAFE_VERSION_FLAGS

    return True


async def run_shell(command: str) -> dict:
    try:
        parts = shlex.split(command)
    except ValueError as e:
        return { "stdout": "", "stderr": f"invalid command: {e}", "returncode": 1 }

    if not is_safe(command):
        return {
            "stdout": "",
            "stderr": f"blocked: '{command}' is not in the allowed command list",
            "returncode": 1,
        }

    print(f"[engineer] running: {command}")
    try:
        proc = await asyncio.create_subprocess_exec(
            *parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        return {
            "stdout": stdout.decode()[:2000],
            "stderr": stderr.decode()[:1000],
            "returncode": proc.returncode,
        }
    except asyncio.TimeoutError:
        return { "stdout": "", "stderr": "command timed out", "returncode": 1 }
    except Exception as e:
        return { "stdout": "", "stderr": str(e), "returncode": 1 }


# ─── GitHub ───────────────────────────────────────────────────────────────────

async def get_open_prs(repo_name: str) -> str:
    if not github_client:
        return "no GitHub token configured"
    try:
        repo = github_client.get_repo(repo_name)
        prs = repo.get_pulls(state="open")
        lines = [f"#{pr.number}: {pr.title} by {pr.user.login}" for pr in prs]
        return "\n".join(lines) if lines else "no open PRs"
    except Exception as e:
        return f"error: {e}"


async def get_recent_issues(repo_name: str) -> str:
    if not github_client:
        return "no GitHub token configured"
    try:
        repo = github_client.get_repo(repo_name)
        issues = repo.get_issues(state="open")
        lines = [f"#{i.number}: {i.title}" for i in list(issues)[:5]]
        return "\n".join(lines) if lines else "no open issues"
    except Exception as e:
        return f"error: {e}"


# ─── Debug stderr ─────────────────────────────────────────────────────────────

ENGINEER_SYSTEM = """You are a debugging assistant. Analyze the error and explain
what went wrong in 1-2 sentences, then suggest the fix. Spoken output — no markdown."""


async def debug_error(stderr: str, command: str) -> str:
    messages = [{
        "role": "user",
        "content": f"Command: {command}\nError:\n{stderr}\n\nWhat went wrong and how do I fix it?"
    }]
    return await llm_complete(
        messages=messages,
        system=ENGINEER_SYSTEM,
        mode="reasoning",
        max_tokens=256,
    )


# ─── Main handler ─────────────────────────────────────────────────────────────

INTENT_SYSTEM = """Extract a safe read-only shell command or GitHub query from the user message.
Respond with JSON only: {"action": "shell"|"github_prs"|"github_issues", "value": "..."}.
Only produce shell commands for inspection, never installs, deletes, moves, copies, writes, or network operations."""


async def engineer_respond(query: str) -> str:
    print(f"[engineer] handling: {query}")

    messages = [{ "role": "user", "content": query }]
    intent_raw = await llm_complete(
        messages=messages,
        system=INTENT_SYSTEM,
        mode="reasoning",
        max_tokens=64,
    )

    import json
    try:
        intent = json.loads(intent_raw)
    except Exception:
        return "hmm, I couldn't parse that command~"

    action = intent.get("action")
    value = intent.get("value", "")

    if action == "shell":
        result = await run_shell(value)
        if result["returncode"] != 0 and result["stderr"]:
            diagnosis = await debug_error(result["stderr"], value)
            return diagnosis
        output = result["stdout"].strip()
        return output[:300] if output else "done~ no output"

    elif action == "github_prs":
        result = await get_open_prs(value)
        return f"open PRs on {value}: {result}"

    elif action == "github_issues":
        result = await get_recent_issues(value)
        return f"open issues on {value}: {result}"

    return "not sure how to handle that~"
