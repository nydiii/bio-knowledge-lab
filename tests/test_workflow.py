import json
import shutil
import sqlite3
import urllib.request
import pytest
from bio_knowledge_lab.cli import main
from bio_knowledge_lab.demo import run_demo,verify_demo
from bio_knowledge_lab.io import read_jsonl,write_jsonl,write_json,digest

@pytest.fixture(scope="module")
def complete_workflow(tmp_path_factory):
    def forbidden(*args,**kwargs):
        raise AssertionError("offline replay attempted network")
    directory=tmp_path_factory.mktemp("workflow")/"complete"
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(urllib.request,"urlopen",forbidden)
        run_demo(directory)
    return directory

@pytest.fixture
def workflow(complete_workflow,tmp_path,monkeypatch):
    def forbidden(*args,**kwargs):
        raise AssertionError("offline verification attempted network")
    monkeypatch.setattr(urllib.request,"urlopen",forbidden)
    directory=tmp_path/"complete"
    shutil.copytree(complete_workflow,directory)
    return directory

def test_complete_free_workflow_has_no_network(workflow):
    report=verify_demo(workflow)
    assert report["passed"]
    assert report["api_calls_in_replay"]==0
    assert not report["scientific_review_complete"]
    assert report["documents"]==50
    reviews=read_jsonl(workflow/"verification_candidates.jsonl")
    assert len(reviews)==50
    assert sum(len(r["judgments"]) for r in reviews)==report["relations"]==690
    assert any(j["label"]=="invalid_judgment" for r in reviews for j in r["judgments"])
    assert report["checks"]["history_relation_transition"]
    assert report["checks"]["repeat_import_idempotent"]

def test_missing_review_file_cannot_pass(workflow):
    (workflow/"verification_candidates.jsonl").unlink()
    with pytest.raises(FileNotFoundError):
        verify_demo(workflow)

@pytest.mark.parametrize("damage",["missing_document","missing_relation","duplicate_relation"])
def test_review_coverage_requires_each_document_and_relation_once(workflow,damage):
    path=workflow/"verification_candidates.jsonl"
    reviews=read_jsonl(path)
    if damage=="missing_document":
        reviews.pop()
    else:
        row=next(r for r in reviews if r["judgments"])
        if damage=="missing_relation": row["judgments"].pop()
        else: row["judgments"].append(row["judgments"][0])
    write_jsonl(path,reviews)
    with pytest.raises(ValueError,match='"evidence_review_coverage": false'):
        verify_demo(workflow)

def test_edited_review_is_not_an_authentic_replay(workflow):
    path=workflow/"verification_candidates.jsonl"
    reviews=read_jsonl(path)
    row=next(r for r in reviews if r["judgments"])
    row["judgments"][0]["reason"]="This is a test alteration, not the model output."
    write_jsonl(path,reviews)
    with pytest.raises(ValueError,match='"evidence_review_replay_match": false'):
        verify_demo(workflow)

def test_history_transition_is_checked_even_with_recomputed_hash(workflow):
    lesson=json.loads((workflow/"revision_lesson.json").read_text(encoding="utf-8"))
    with sqlite3.connect(workflow/"knowledge.sqlite") as connection:
        original=connection.execute("SELECT record_json FROM snapshots WHERE doc_id=? AND version=1",(lesson["doc_id"],)).fetchone()[0]
        # Leave the expected kind/version and old query files intact, but erase
        # the injected change in the actual historical snapshot.
        connection.execute("UPDATE snapshots SET record_json=?,record_hash=? WHERE doc_id=? AND version=2",
                           (original,digest(original),lesson["doc_id"]))
    with pytest.raises(ValueError,match='"history_relation_transition": false'):
        verify_demo(workflow)

def test_history_record_hash_is_recomputed(workflow):
    with sqlite3.connect(workflow/"knowledge.sqlite") as connection:
        connection.execute("UPDATE snapshots SET record_hash=? WHERE version=1",("0"*64,))
    with pytest.raises(ValueError,match='"history_hashes": false'):
        verify_demo(workflow)

def test_repeat_import_result_must_report_no_additions(workflow):
    path=workflow/"run_metadata.json"
    metadata=json.loads(path.read_text(encoding="utf-8"))
    metadata["repeat_import"]["added"]=1
    write_json(path,metadata)
    with pytest.raises(ValueError,match='"repeat_import_idempotent": false'):
        verify_demo(workflow)
    assert main(["verify","--workdir",str(workflow)])==2

def test_extra_version_from_repeated_import_cannot_pass(workflow):
    lesson=json.loads((workflow/"revision_lesson.json").read_text(encoding="utf-8"))
    with sqlite3.connect(workflow/"knowledge.sqlite") as connection:
        doc_id=connection.execute("SELECT doc_id FROM documents WHERE doc_id!=? LIMIT 1",(lesson["doc_id"],)).fetchone()[0]
        connection.execute("INSERT INTO snapshots SELECT doc_id,2,record_json,record_hash,created_at,kind,reason,actor,evidence_json FROM snapshots WHERE doc_id=? AND version=1",(doc_id,))
        connection.execute("UPDATE documents SET current_version=2 WHERE doc_id=?",(doc_id,))
    with pytest.raises(ValueError,match='"history_versions": false'):
        verify_demo(workflow)
