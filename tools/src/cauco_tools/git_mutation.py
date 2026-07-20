import re
from dataclasses import dataclass
from pathlib import PurePosixPath


MAX_GIT_ADD_PATHS = 20
MAX_GIT_COMMIT_MESSAGE = 120
ABSENT_REMOTE_COMMIT = "ABSENT"


@dataclass(frozen=True, slots=True)
class GitAddInput:
    """Immutable approved input for the single supported Git mutation."""

    paths: tuple[str, ...]

    def __post_init__(self) -> None:
        paths = tuple(self.paths)
        if not paths:
            raise ValueError("git.add requires at least one exact path.")
        if len(paths) > MAX_GIT_ADD_PATHS:
            raise ValueError(f"git.add accepts at most {MAX_GIT_ADD_PATHS} paths.")
        normalized: list[str] = []
        for raw in paths:
            if (
                not isinstance(raw, str)
                or not raw
                or raw != raw.strip()
                or "\x00" in raw
            ):
                raise ValueError(
                    "git.add paths must be non-empty workspace-relative text."
                )
            if (
                "\\" in raw
                or raw.startswith(("/", "-"))
                or re.match(r"^[A-Za-z]:", raw)
            ):
                raise ValueError(
                    "git.add paths must be exact workspace-relative paths."
                )
            path = PurePosixPath(raw)
            if raw in {".", ":/"} or any(
                part in {"", ".", ".."} for part in path.parts
            ):
                raise ValueError(
                    "git.add paths cannot select a root or traverse directories."
                )
            if any(character in raw for character in "*?[]{}") or raw.startswith(
                (":", "!", "^")
            ):
                raise ValueError("git.add wildcard and pathspec syntax is forbidden.")
            value = path.as_posix()
            if value.casefold() == ".git" or value.casefold().startswith(".git/"):
                raise ValueError("git.add cannot target Git internals.")
            normalized.append(value)
        if len({item.casefold() for item in normalized}) != len(normalized):
            raise ValueError("git.add paths must be unique after normalization.")
        object.__setattr__(self, "paths", tuple(normalized))


@dataclass(frozen=True, slots=True)
class GitCommitInput:
    """Immutable approved input for one local commit of the existing index."""

    message: str
    expected_staged_paths: tuple[str, ...]
    intent_summary: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.message, str):
            raise ValueError("git.commit requires a UTF-8 text message.")
        message = self.message.strip()
        if (
            not message
            or len(message) > MAX_GIT_COMMIT_MESSAGE
            or "\n" in message
            or "\r" in message
            or "\x00" in message
            or any(ord(character) < 32 or ord(character) == 127 for character in message)
            or message.casefold().startswith(("fixup!", "squash!"))
            or message.startswith("-")
        ):
            raise ValueError("git.commit message does not meet the Phase 7C policy.")
        if re.search(r"(?:api[_ -]?key|password|secret|token)\s*[:=]", message, re.I):
            raise ValueError("git.commit message appears to contain credential material.")
        paths = GitAddInput(tuple(self.expected_staged_paths)).paths
        if self.intent_summary is not None and (
            not isinstance(self.intent_summary, str) or "\x00" in self.intent_summary
        ):
            raise ValueError("git.commit intent summary must be safe text.")
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "expected_staged_paths", paths)


def _git_name(value: str, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or value.startswith("-")
        or any(character.isspace() or ord(character) < 32 for character in value)
        or any(token in value for token in ("\\", ":", "..", "@{", "~", "^", "?", "*", "["))
        or value.endswith((".", ".lock"))
        or "//" in value
    ):
        raise ValueError(f"git.push {label} is not a safe exact Git name.")
    return value


@dataclass(frozen=True, slots=True)
class GitPushInput:
    """Immutable approved input for publishing one exact local branch tip."""

    remote: str
    local_branch: str
    remote_branch: str
    expected_local_commit: str
    expected_remote_commit: str
    intent_summary: str | None = None

    def __post_init__(self) -> None:
        remote = _git_name(self.remote, label="remote")
        local_branch = _git_name(self.local_branch, label="local branch")
        remote_branch = _git_name(self.remote_branch, label="remote branch")
        if local_branch != remote_branch:
            raise ValueError("git.push requires matching local and remote branch names.")
        if not re.fullmatch(r"[0-9a-f]{40,64}", self.expected_local_commit):
            raise ValueError("git.push requires an exact local commit ID.")
        if self.expected_remote_commit != ABSENT_REMOTE_COMMIT and not re.fullmatch(
            r"[0-9a-f]{40,64}", self.expected_remote_commit
        ):
            raise ValueError("git.push requires an exact remote commit ID or ABSENT.")
        if self.intent_summary is not None and (
            not isinstance(self.intent_summary, str) or "\x00" in self.intent_summary
        ):
            raise ValueError("git.push intent summary must be safe text.")
        object.__setattr__(self, "remote", remote)
        object.__setattr__(self, "local_branch", local_branch)
        object.__setattr__(self, "remote_branch", remote_branch)
