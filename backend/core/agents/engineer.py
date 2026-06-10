import asyncio
import shlex
from pathlib import Path
from github import Github
from core.llm_client import llm_complete
from config import ENGINEER_WORKSPACE_ROOT, GITHUB_TOKEN

github_client = Github(GITHUB_TOKEN) if GITHUB_TOKEN else None

# ─── Allowed shell commands ───────────────────────────────────────────────────

ALLOWED_COMMANDS = [
    "ls", "pwd", "echo", "cat", "grep", "find",
    "git", "python", "node", "npm",
]

BLOCKED = ["rm -rf", "sudo", "chmod 777", "dd if", "> /dev/"]
SHELL_METACHARS = {";", "&", "|", ">", "<", "`", "$", "(", ")", "\n"}
MAX_COMMAND_LENGTH = 512
MAX_ARG_COUNT = 32
SAFE_GIT_SUBCOMMANDS = {
    "status", "log", "show", "diff", "branch", "remote", "rev-parse",
}
SAFE_VERSION_FLAGS = {"--version", "-v", "version"}
WORKSPACE_ROOT = Path(ENGINEER_WORKSPACE_ROOT).expanduser().resolve()
PATH_COMMANDS = {"ls", "cat", "grep", "find"}
PATH_VALUE_OPTIONS = {
    "-C",
    "--git-dir",
    "--work-tree",
    "-f",
    "--file",
    "--exclude-from",
}
FIND_VALUE_OPTIONS = {
    "-maxdepth",
    "-mindepth",
    "-name",
    "-iname",
    "-type",
    "-size",
    "-mtime",
    "-newer",
}
FIND_PATH_VALUE_OPTIONS = {"-newer"}
GREP_VALUE_OPTIONS = {
    "-A",
    "-B",
    "-C",
    "--after-context",
    "--before-context",
    "--context",
    "--exclude",
    "--include",
    "--exclude-dir",
}
GREP_PATH_VALUE_OPTIONS = {"-f", "--file"}
GREP_PATTERN_VALUE_OPTIONS = {"-e", "--regexp"}


def _is_workspace_path(path: Path) -> bool:
    try:
        path.relative_to(WORKSPACE_ROOT)
        return True
    except ValueError:
        return False


def resolve_workspace_path(raw_path: str) -> Path | None:
    if raw_path in {"", "."}:
        return WORKSPACE_ROOT
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = WORKSPACE_ROOT / candidate
    resolved = candidate.resolve(strict=False)
    if not _is_workspace_path(resolved):
        return None
    return resolved


def _looks_like_path(value: str) -> bool:
    if value in {".", ".."}:
        return True
    path_suffixes = (
        ".py", ".ts", ".tsx", ".js", ".json", ".md", ".txt", ".toml",
        ".yaml", ".yml",
    )
    return (
        value.startswith(("/", "~/", "./", "../"))
        or "/" in value
        or value.endswith(path_suffixes)
    )


def _validate_workspace_operand(value: str) -> bool:
    return resolve_workspace_path(value) is not None


def _validate_git(parts: list[str]) -> bool:
    if len(parts) < 2:
        return False
    if parts[1] not in SAFE_GIT_SUBCOMMANDS:
        return False

    skip_next = False
    for arg in parts[2:]:
        if skip_next:
            if not _validate_workspace_operand(arg):
                return False
            skip_next = False
            continue
        if arg in PATH_VALUE_OPTIONS:
            skip_next = True
            continue
        if arg.startswith("--git-dir=") or arg.startswith("--work-tree="):
            _, value = arg.split("=", 1)
            if not _validate_workspace_operand(value):
                return False
        elif _looks_like_path(arg) and not _validate_workspace_operand(arg):
            return False

    return not skip_next


def _validate_path_command(base: str, parts: list[str]) -> bool:
    mutating_find_args = {"-exec", "-delete", "-execdir", "-ok", "-okdir"}
    if base == "find" and any(arg in mutating_find_args for arg in parts[1:]):
        return False

    if base == "cat" and len(parts) == 1:
        return False

    if base == "find":
        if len(parts) == 1:
            return True
        skip_next = False
        for arg in parts[1:]:
            if skip_next:
                if skip_next == "path" and not _validate_workspace_operand(arg):
                    return False
                skip_next = False
                continue
            if arg in FIND_PATH_VALUE_OPTIONS:
                skip_next = "path"
                continue
            if arg in FIND_VALUE_OPTIONS:
                skip_next = "value"
                continue
            if arg.startswith("-"):
                continue
            if not _validate_workspace_operand(arg):
                return False
        return not skip_next

    if base == "grep":
        skip_next = ""
        saw_pattern = False
        saw_path = False
        for arg in parts[1:]:
            if skip_next:
                if skip_next == "path" and not _validate_workspace_operand(arg):
                    return False
                if skip_next in {"path", "pattern"}:
                    saw_pattern = True
                skip_next = False
                continue
            if arg in GREP_PATH_VALUE_OPTIONS:
                skip_next = "path"
                continue
            if arg in GREP_PATTERN_VALUE_OPTIONS:
                skip_next = "pattern"
                continue
            if arg in GREP_VALUE_OPTIONS:
                skip_next = "value"
                continue
            if arg.startswith("-"):
                continue
            if not saw_pattern:
                saw_pattern = True
                continue
            if not _validate_workspace_operand(arg):
                return False
            saw_path = True
        return not skip_next and saw_pattern and saw_path

    for arg in parts[1:]:
        if arg.startswith("-"):
            continue
        if not _validate_workspace_operand(arg):
            return False
    return True


def is_safe(command: str) -> bool:
    cmd = command.strip().lower()
    if len(command) > MAX_COMMAND_LENGTH:
        return False
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
    if len(parts) > MAX_ARG_COUNT:
        return False

    base = parts[0]
    if base not in ALLOWED_COMMANDS:
        return False

    if base in PATH_COMMANDS:
        return _validate_path_command(base, parts)

    if base == "git":
        return _validate_git(parts)

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
            cwd=str(WORKSPACE_ROOT),
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

INTENT_SYSTEM = """Extract a safe read-only shell command or GitHub query from the user message or task brief.
Respond with JSON only: {"action": "shell"|"github_prs"|"github_issues", "value": "..."}.
Only produce shell commands for inspection, never installs, deletes, moves, copies, writes, or network operations."""


def _format_task_brief(query: str, task: dict | None, original_request: str | None, previous_results: list[dict] | None) -> str:
    if not task:
        return query

    parts = [
        f"Original user request: {original_request or query}",
        f"Task objective: {task.get('objective', '')}",
        f"Task input: {task.get('input', query)}",
        f"Success criteria: {task.get('success_criteria', '')}",
    ]
    if previous_results:
        prior = "\n".join([
            f"- {r.get('agent')} {r.get('task_id')}: {r.get('result')}"
            for r in previous_results
        ])
        parts.append(f"Previous subagent results:\n{prior}")
    return "\n".join(parts)


async def engineer_respond(
    query: str,
    task: dict | None = None,
    original_request: str | None = None,
    previous_results: list[dict] | None = None,
) -> str:
    print(f"[engineer] handling: {query}")
    task_brief = _format_task_brief(query, task, original_request, previous_results)

    messages = [{ "role": "user", "content": task_brief }]
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
