"""Frozen teaching data must not silently change on a rebuild."""
import importlib.util
import json
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location(
    "prepare_data", Path(__file__).resolve().parents[1] / "scripts/prepare_data.py"
)
prep = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prep)


def test_json_serialization_is_key_order_independent(tmp_path):
    left, right = tmp_path / "left.json", tmp_path / "right.json"
    prep.dump(left, {"z": {"b": 1, "a": 2}, "a": 3})
    prep.dump(right, {"a": 3, "z": {"a": 2, "b": 1}})
    assert left.read_bytes() == right.read_bytes()


def staged_fixture(tmp_path, monkeypatch):
    root, stage = tmp_path / "repo", tmp_path / "stage"
    monkeypatch.setattr(prep, "ROOT", root)
    path = "data/reference/gold.jsonl"
    (root / path).parent.mkdir(parents=True)
    (root / path).write_text("original gold\n")
    (stage / path).parent.mkdir(parents=True)
    (stage / path).write_text("changed gold\n")
    old = {"sources": [{"file": "source.zip", "url": "https://example.org/source.zip", "sha256": "source-hash"}],
           "artifacts": [{"path": path, "sha256": prep.sha(root / path)}]}
    new = {"sources": old["sources"], "artifacts": [{"path": path, "sha256": prep.sha(stage / path)}]}
    prep.dump(root / "data/manifest.json", old)
    prep.dump(stage / "data/manifest.json", new)
    return root, stage, path, old


def test_changed_rebuild_does_not_replace_gold_or_manifest(tmp_path, monkeypatch):
    root, stage, path, old = staged_fixture(tmp_path, monkeypatch)
    before = (root / "data/manifest.json").read_bytes()
    with pytest.raises(ValueError, match="no bundled files were replaced"):
        prep.publish_staged(stage, [path], old)
    assert (root / path).read_text() == "original gold\n"
    assert (root / "data/manifest.json").read_bytes() == before


def test_explicit_refresh_replaces_lock_and_artifact_together(tmp_path, monkeypatch):
    root, stage, path, old = staged_fixture(tmp_path, monkeypatch)
    prep.publish_staged(stage, [path], old, refresh_lock=True)
    assert (root / path).read_text() == "changed gold\n"
    manifest = json.loads((root / "data/manifest.json").read_text())
    assert manifest["artifacts"][0]["sha256"] == prep.sha(root / path)


def test_changed_source_rejected_even_if_artifact_same(tmp_path, monkeypatch):
    root, stage, path, old = staged_fixture(tmp_path, monkeypatch)
    (stage / path).write_bytes((root / path).read_bytes())
    new = json.loads(json.dumps(old))
    new["sources"][0]["sha256"] = "unexpected-new-source"
    prep.dump(stage / "data/manifest.json", new)
    with pytest.raises(ValueError, match="Rebuild differs"):
        prep.publish_staged(stage, [path], old)
    assert (root / path).read_text() == "original gold\n"
