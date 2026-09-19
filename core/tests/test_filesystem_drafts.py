from pathlib import Path
from uuid import UUID

import pytest

from cauco_core.filesystem_drafts import DraftOwnershipError, DraftStateError, DraftStatus, FilesystemDraftStore


ONE = UUID("00000000-0000-4000-8000-000000000001")
TWO = UUID("00000000-0000-4000-8000-000000000002")


def store(tmp_path: Path) -> FilesystemDraftStore:
    workspace = tmp_path / "workspace"; workspace.mkdir()
    return FilesystemDraftStore(workspace)


def test_create_persists_without_creating_target(tmp_path: Path) -> None:
    value = store(tmp_path); draft = value.create(ONE, "note.txt", "hello")
    assert (value.root / f"{draft.draft_id}.json").exists()
    assert not (value.workspace / "note.txt").exists()
    assert value.get(draft.draft_id).digest == draft.digest


def test_reinstantiation_and_conversations_are_isolated(tmp_path: Path) -> None:
    value = store(tmp_path); first = value.create(ONE, "one.txt", "one"); second = value.create(TWO, "two.txt", "two")
    restored = FilesystemDraftStore(value.workspace)
    assert restored.get_active_by_conversation(ONE).draft_id == first.draft_id
    assert restored.get_active_by_conversation(TWO).draft_id == second.draft_id


def test_update_ownership_and_terminal_states(tmp_path: Path) -> None:
    value = store(tmp_path); draft = value.create(ONE, "note.txt", "one")
    updated = value.update(draft.draft_id, ONE, "two")
    assert updated.draft_id == draft.draft_id and updated.digest != draft.digest
    with pytest.raises(DraftOwnershipError): value.update(draft.draft_id, TWO, "no")
    assert value.mark_finalized(draft.draft_id, ONE).status is DraftStatus.FINALIZED
    with pytest.raises(DraftStateError): value.update(draft.draft_id, ONE, "no")


def test_cancel_and_one_active_draft(tmp_path: Path) -> None:
    value = store(tmp_path); draft = value.create(ONE, "note.txt", "one")
    with pytest.raises(DraftStateError): value.create(ONE, "other.txt", "two")
    assert value.cancel(draft.draft_id, ONE).status is DraftStatus.CANCELLED
    with pytest.raises(DraftStateError): value.mark_finalized(draft.draft_id, ONE)


@pytest.mark.parametrize("vocative", ["", "Cauco,", "Cauco ", "Cojo,", "Cojo "])
@pytest.mark.parametrize("extension", ["txt", "md", "json", "yaml", "yml", "toml"])
@pytest.mark.parametrize("separator", [": ", " "])
def test_requested_workspace_write_bounded_dictation(vocative, extension, separator):
    from cauco_agents.builtin.filesystem_agent import requested_workspace_write

    content = 'Cauco, punto txt y punto md.\n{"literal": "punto json"}?!  \n'
    result = requested_workspace_write(
        f"{vocative}crea un archivo prueba punto {extension} con este contenido{separator}{content}"
    )
    assert result is not None
    assert result.relative_path == f"prueba.{extension}"
    assert result.content == content
    assert result.overwrite_policy == "create_only"


@pytest.mark.parametrize("instruction", [
    "Caucoo, crea un archivo prueba punto txt con contenido hola",
    "Por favor crea un archivo prueba punto txt con contenido hola",
    "crea un archivo prueba punto pdf con contenido hola",
    "crea un archivo ../prueba punto txt con contenido hola",
    "crea un archivo /tmp/prueba punto txt con contenido hola",
    "crea un archivo prueba punto txt extra con contenido hola",
    "crea un archivo prueba punto txt",
])
def test_requested_workspace_write_rejects_outside_bounded_grammar(instruction):
    from cauco_agents.builtin.filesystem_agent import requested_workspace_write

    assert requested_workspace_write(instruction) is None


@pytest.mark.parametrize("verb,policy", [("crea", "create_only"), ("reemplaza", "replace_existing")])
def test_requested_workspace_write_literal_filename_and_content(verb, policy):
    from cauco_agents.builtin.filesystem_agent import requested_workspace_write

    result = requested_workspace_write(f"{verb} archivo prueba.txt con contenido hola punto yaml!")
    assert result is not None
    assert result.relative_path == "prueba.txt"
    assert result.content == "hola punto yaml!"
    assert result.overwrite_policy == policy
