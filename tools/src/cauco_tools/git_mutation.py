import re
from dataclasses import dataclass
from pathlib import PurePosixPath


MAX_GIT_ADD_PATHS = 20
MAX_GIT_COMMIT_MESSAGE = 120


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
