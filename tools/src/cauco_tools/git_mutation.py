import re
from dataclasses import dataclass
from pathlib import PurePosixPath


MAX_GIT_ADD_PATHS = 20


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
