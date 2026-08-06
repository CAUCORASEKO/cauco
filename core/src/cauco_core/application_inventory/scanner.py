"""Bounded, read-only macOS application bundle scanner."""

from __future__ import annotations

import hashlib
import plistlib
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path

from .models import ApplicationAvailability, ApplicationBundleSnapshot, ApplicationSource

DEFAULT_ROOTS = (
    (Path("/Applications"), ApplicationSource.LOCAL_APPLICATIONS),
    (Path("/System/Applications"), ApplicationSource.SYSTEM_APPLICATIONS),
    (Path("/System/Applications/Utilities"), ApplicationSource.SYSTEM_APPLICATIONS),
    (Path.home() / "Applications", ApplicationSource.USER_APPLICATIONS),
)


class ApplicationScanner:
    def __init__(
        self,
        roots: Iterable[tuple[Path, ApplicationSource]] | None = None,
        clock: Callable[[], datetime] | None = None,
        max_entries: int = 500,
        max_results: int = 100,
    ) -> None:
        if not 1 <= max_entries <= 5000 or not 1 <= max_results <= 500:
            raise ValueError("Scan bounds are invalid.")
        self.roots = tuple((Path(path), source) for path, source in (roots or DEFAULT_ROOTS))
        self.clock = clock or (lambda: datetime.now().astimezone())
        self.max_entries = max_entries
        self.max_results = max_results

    def scan(self) -> tuple[ApplicationBundleSnapshot, ...]:
        snapshots: dict[str, ApplicationBundleSnapshot] = {}
        entries_seen = 0
        for root, source in sorted(self.roots, key=lambda item: str(item[0])):
            if not root.exists() or not root.is_dir() or root.is_symlink():
                continue
            try:
                entries = sorted(root.iterdir(), key=lambda item: item.name.casefold())
            except OSError:
                continue
            for entry in entries:
                entries_seen += 1
                if entries_seen > self.max_entries:
                    break
                if (
                    entry.name.startswith(".")
                    or entry.suffix.casefold() != ".app"
                    or entry.is_symlink()
                ):
                    continue
                snapshot = self._inspect(entry, source)
                key = snapshot.bundle_identifier or snapshot.bundle_path
                current = snapshots.get(key)
                if current is None or snapshot.bundle_path < current.bundle_path:
                    snapshots[key] = snapshot
        return tuple(
            sorted(snapshots.values(), key=lambda item: (item.normalized_name, item.bundle_path))[
                : self.max_results
            ]
        )

    def _inspect(self, bundle: Path, source: ApplicationSource) -> ApplicationBundleSnapshot:
        path = bundle / "Contents" / "Info.plist"
        values = {}
        reasons: list[str] = []
        availability = ApplicationAvailability.AVAILABLE
        try:
            with path.open("rb") as handle:
                values = plistlib.load(handle)
            if not isinstance(values, dict):
                raise ValueError("plist root is not a dictionary")
        except FileNotFoundError:
            availability = ApplicationAvailability.INVALID_BUNDLE
            reasons.append("info_plist_missing")
        except (OSError, plistlib.InvalidFileException, ValueError, TypeError):
            availability = ApplicationAvailability.UNREADABLE
            reasons.append("info_plist_unreadable")
        display_name = (
            self._string(values, "CFBundleDisplayName")
            or self._string(values, "CFBundleName")
            or bundle.stem
        )
        bundle_id = self._string(values, "CFBundleIdentifier")
        stable = hashlib.sha256((bundle_id or str(bundle)).encode()).hexdigest()[:32]
        return ApplicationBundleSnapshot(
            inventory_id=f"app_{stable}",
            display_name=display_name,
            normalized_name="",
            bundle_identifier=bundle_id,
            bundle_path=str(bundle.resolve()),
            bundle_filename=bundle.name,
            version=self._string(values, "CFBundleShortVersionString"),
            build_version=self._string(values, "CFBundleVersion"),
            minimum_macos_version=self._string(values, "LSMinimumSystemVersion"),
            source=source,
            availability=availability,
            localizations=self._strings(values.get("CFBundleLocalizations")),
            url_schemes=self._url_schemes(values.get("CFBundleURLTypes")),
            document_types=self._document_types(values.get("CFBundleDocumentTypes")),
            diagnostic_reason_codes=tuple(reasons),
            discovered_at=self.clock(),
            limitations=(
                "No application content, permissions, processes, or private data are inspected.",
            ),
        )

    @staticmethod
    def _string(values: dict, key: str) -> str | None:
        value = values.get(key)
        return value if isinstance(value, str) and value and len(value) <= 500 else None

    @staticmethod
    def _strings(value: object) -> tuple[str, ...]:
        if not isinstance(value, list):
            return ()
        return tuple(item for item in value if isinstance(item, str) and len(item) <= 100)

    @classmethod
    def _url_schemes(cls, value: object) -> tuple[str, ...]:
        result = []
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    result.extend(cls._strings(item.get("CFBundleURLSchemes")))
        return tuple(result)

    @classmethod
    def _document_types(cls, value: object) -> tuple[str, ...]:
        result = []
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    result.extend(cls._strings(item.get("LSItemContentTypes")))
        return tuple(result)
