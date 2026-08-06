"""Focused tests for the bounded application inventory."""

import plistlib
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cauco_core.application_inventory import ApplicationInventoryService, ApplicationScanner
from cauco_core.application_inventory.exceptions import ApplicationNotFoundError
from cauco_core.application_inventory.models import (
    ApplicationAvailability,
    ApplicationBundleSnapshot,
    ApplicationSource,
)


def make_app(root: Path, name: str, values: dict) -> Path:
    bundle = root / name
    (bundle / "Contents").mkdir(parents=True)
    with (bundle / "Contents" / "Info.plist").open("wb") as handle:
        plistlib.dump(values, handle)
    return bundle


def scanner(root: Path, **kwargs) -> ApplicationScanner:
    return ApplicationScanner(
        ((root, ApplicationSource.EXPLICIT_PATH),),
        clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        **kwargs,
    )


def test_scans_allowlisted_app_metadata_only(tmp_path):
    make_app(
        tmp_path,
        "Éditor.app",
        {
            "CFBundleIdentifier": "com.example.editor",
            "CFBundleDisplayName": "Éditeur",
            "CFBundleShortVersionString": "1",
            "CFBundleURLTypes": [{"CFBundleURLSchemes": ["z", "z", "a"]}],
            "CFBundleLocalizations": ["fi", "en", "fi"],
            "PrivateSecret": "hidden",
        },
    )
    (tmp_path / "not-an-app.txt").write_text("x")
    item = scanner(tmp_path).scan()[0]
    assert item.display_name == "Éditeur"
    assert item.normalized_name == "editeur"
    assert item.url_schemes == ("a", "z")
    assert item.localizations == ("en", "fi")
    assert not hasattr(item, "PrivateSecret")


def test_scanner_handles_malformed_and_missing_plists(tmp_path):
    malformed = tmp_path / "Bad.app" / "Contents"
    malformed.mkdir(parents=True)
    (malformed / "Info.plist").write_bytes(b"not plist")
    (tmp_path / "Missing.app" / "Contents").mkdir(parents=True)
    results = scanner(tmp_path).scan()
    assert {item.availability for item in results} == {
        ApplicationAvailability.UNREADABLE,
        ApplicationAvailability.INVALID_BUNDLE,
    }


def test_scanner_ignores_hidden_and_symlink_bundles(tmp_path):
    make_app(tmp_path, "Visible.app", {"CFBundleName": "Visible"})
    make_app(tmp_path, ".Hidden.app", {"CFBundleName": "Hidden"})
    external = tmp_path / "external"
    external.mkdir()
    make_app(external, "Outside.app", {"CFBundleName": "Outside"})
    (tmp_path / "Link.app").symlink_to(external / "Outside.app", target_is_directory=True)
    assert [item.bundle_filename for item in scanner(tmp_path).scan()] == ["Visible.app"]


def test_scanner_is_bounded_and_deterministic(tmp_path):
    for index in range(5):
        make_app(tmp_path, f"{index}.app", {"CFBundleName": str(index)})
    assert len(scanner(tmp_path, max_entries=2).scan()) <= 2
    assert [item.bundle_filename for item in scanner(tmp_path).scan()] == [
        f"{i}.app" for i in range(5)
    ]


def test_model_is_frozen_and_validates_timestamp_and_architecture():
    values = dict(
        inventory_id="app_one",
        display_name="One",
        normalized_name="one",
        bundle_identifier=None,
        bundle_path="/Applications/One.app",
        bundle_filename="One.app",
        version=None,
        build_version=None,
        minimum_macos_version=None,
        source=ApplicationSource.EXPLICIT_PATH,
        availability=ApplicationAvailability.AVAILABLE,
        discovered_at=datetime.now(UTC),
    )
    item = ApplicationBundleSnapshot(**values)
    with pytest.raises(FrozenInstanceError):
        item.display_name = "Two"  # type: ignore[misc]
    with pytest.raises(ValueError):
        ApplicationBundleSnapshot(**{**values, "architecture": "mips"})
    with pytest.raises(ValueError):
        ApplicationBundleSnapshot(**{**values, "discovered_at": datetime.now()})


def test_service_refresh_list_search_filters_and_get(tmp_path):
    make_app(
        tmp_path, "Mail.app", {"CFBundleIdentifier": "com.example.mail", "CFBundleName": "Mail"}
    )
    service = ApplicationInventoryService(scanner(tmp_path))
    assert service.status().scan_state == "empty"
    service.refresh()
    assert service.list(query="mail")[0].bundle_identifier == "com.example.mail"
    assert service.get(service.list()[0].inventory_id).display_name == "Mail"
    with pytest.raises(ApplicationNotFoundError):
        service.get("app_missing")


def test_refresh_replaces_previous_snapshot(tmp_path):
    make_app(tmp_path, "First.app", {"CFBundleName": "First"})
    service = ApplicationInventoryService(scanner(tmp_path))
    service.refresh()
    (tmp_path / "First.app").rename(tmp_path / "Second.app")
    service.refresh()
    assert [item.bundle_filename for item in service.list()] == ["Second.app"]
