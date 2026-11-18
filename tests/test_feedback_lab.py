"""The lesson must run offline and keep prediction distinct from reference."""
import json

import pytest

from copy import deepcopy
from bio_knowledge_lab.feedback_lab import run_feedback_lab, _validate_comparable
from bio_knowledge_lab.io import DATA


def test_missing_prerequisites_explain_next_step(tmp_path):
    with pytest.raises(ValueError, match="baseline"):
        run_feedback_lab("optimize", tmp_path / "missing")


@pytest.mark.parametrize("changed", ["document", "text", "entity", "span", "relation", "endpoint", "novelty"])
def test_comparison_rejects_changed_denominator_or_task(changed):
    old = [{"doc_id": "example", "text": "A B", "entities": [
        {"mention_id": "m1", "text": "A", "type": "Gene", "start": 0, "end": 1},
        {"mention_id": "m2", "text": "B", "type": "Gene", "start": 2, "end": 3}],
        "relations": [{"relation_id": "r1", "head": "m1", "tail": "m2", "type": "Association", "novelty": "No"}]}]
    new = deepcopy(old)
    if changed == "document": new.pop()
    elif changed == "text": new[0]["text"] = "A C"
    elif changed == "entity": new[0]["entities"].pop()
    elif changed == "span": new[0]["entities"][0]["end"] = 2
    elif changed == "relation": new[0]["relations"].pop()
    elif changed == "endpoint": new[0]["relations"][0]["head"] = "m2"
    else: new[0]["relations"][0]["novelty"] = "Novel"
    with pytest.raises(ValueError):
        _validate_comparable(old, new)


def test_complete_lesson_offline_and_originals_immutable(tmp_path, monkeypatch):
    import urllib.request
    def no_network(*args, **kwargs):
        raise AssertionError("The free lesson must not use network")
    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    folder = tmp_path / "lesson"
    gold = (DATA / "reference/gold.jsonl").read_bytes()
    result = run_feedback_lab("baseline", folder)
    assert result["api_calls"] == 0 and result["documents"] == 50
    original = (folder / "baseline.jsonl").read_bytes()
    before = json.loads((folder / "baseline_evaluation.json").read_text())
    assert before["linking_strict"]["true_positive"] == 1249
    with pytest.raises(ValueError, match="新"):
        run_feedback_lab("baseline", folder)
    with pytest.raises(ValueError, match="optimize"):
        run_feedback_lab("compare", folder)
    run_feedback_lab("inspect", folder)
    assert "不用" in (folder / "inspection.md").read_text(encoding="utf-8")
    run_feedback_lab("optimize", folder)
    run_feedback_lab("compare", folder)
    comparison = json.loads((folder / "comparison.json").read_text())
    assert comparison["new_api_calls"] == 0
    assert comparison["scientific_review_complete"] is False
    groups = comparison["groups"]
    assert groups["开发案例"]["before"]["evaluated_documents"] == 10
    assert groups["本轮未参与调整的验证文献"]["before"]["evaluated_documents"] == 40
    for scores in groups.values():
        assert scores["before"]["ner_strict"] == scores["after"]["ner_strict"]
    changed = {(r["doc_id"], r["relation_id"]) for r in comparison["relation_changes"]}
    assert changed == {("19672862", "r14"), ("19672862", "r15"), ("21750150", "r10")}
    assert (folder / "baseline.jsonl").read_bytes() == original
    assert (DATA / "reference/gold.jsonl").read_bytes() == gold
    with pytest.raises(ValueError, match="已经存在"):
        run_feedback_lab("optimize", folder)
    path = folder / "improved.jsonl"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="手改"):
        run_feedback_lab("compare", folder)
    (folder / "baseline.jsonl").write_bytes(original + b"\n")
    with pytest.raises(ValueError, match="旧版文件"):
        run_feedback_lab("inspect", folder)
