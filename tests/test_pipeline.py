"""Synthetic fixtures test software invariants; these are not scientific gold."""
from copy import deepcopy
import json

import pytest

from bio_knowledge_lab.pipeline import (
    align_records, apply_revision, current_records, evaluate_records, history,
    ingest_records, query_database, validate_database, _propagate_document_abbreviations,
)
from bio_knowledge_lab.retrieval import retrieve_evidence


def make_record(doc_id="p1", text="In humans, human TP53 is associated with cancer.", relation_type="Association"):
    entities = []
    for mid, surface, kind in [("e1", "TP53", "GeneOrGeneProduct"),
                                ("e2", "cancer", "DiseaseOrPhenotypicFeature"),
                                ("e3", "humans", "OrganismTaxon")]:
        if surface in text:
            start = text.index(surface)
            entities.append({"mention_id": mid, "text": surface, "start": start,
                             "end": start + len(surface), "type": kind})
    return {"doc_id": doc_id, "text": text, "entities": entities,
            "relations": [{"relation_id": "r1", "head": "e1", "tail": "e2", "type": relation_type,
                           "novelty": "Novel", "evidence": [{"start": 0, "end": len(text), "text": text}], "context": {}}]}


@pytest.fixture
def kb(tmp_path):
    terms = [
        {"namespace": "NCBIGene", "id": "7157", "name": "TP53", "aliases": ["p53"], "type": "Gene", "tax_id": "9606", "source": "external-test-kb"},
        {"namespace": "NCBIGene", "id": "22059", "name": "Trp53", "aliases": ["p53", "TP53"], "type": "Gene", "tax_id": "10090", "source": "external-test-kb"},
        {"namespace": "MESH", "id": "D009369", "name": "Neoplasms", "aliases": ["cancer"], "type": "Disease", "source": "external-test-kb"},
        {"namespace": "NCBITaxon", "id": "9606", "name": "Homo sapiens", "aliases": ["humans", "human"], "type": "Species", "tax_id": "9606", "source": "external-test-kb"},
    ]
    path = tmp_path / "kb.jsonl"
    path.write_text("\n".join(json.dumps(term) for term in terms), encoding="utf-8")
    return path


def test_ambiguous_same_alias_does_not_merge_species(kb):
    record = make_record(text="TP53 is associated with cancer.")
    record["entities"][0]["tax_id"] = "9606"  # Untrusted model assertion must not resolve identity.
    aligned = align_records([record], kb)[0]
    gene = aligned["entities"][0]
    assert gene["link_status"] == "ambiguous"
    assert gene["links"] == []
    assert {x["id"] for x in gene["link_candidates"]} == {"7157", "22059"}
    assert "links" not in record["entities"][0]


def test_explicit_taxon_resolves_compatible_alias(kb):
    aligned = align_records([make_record()], kb)[0]
    assert aligned["entities"][0]["links"][0]["id"] == "7157"
    assert aligned["entities"][0]["taxon_context"]["basis"] == "explicit_adjacent_species_qualifier"
    assert aligned["alignment"]["gold_used"] is False


def test_unseen_name_is_preserved(kb):
    record = make_record()
    record["text"] = record["text"].replace("TP53", "ZZZZ")
    record["entities"][0]["text"] = "ZZZZ"
    aligned = align_records([record], kb)[0]
    assert aligned["entities"][0]["link_status"] == "unresolved"
    assert len(aligned["relations"]) == 1


def test_cross_document_evidence_and_disagreement_retained(tmp_path, kb):
    records = align_records([make_record(), make_record("p2", relation_type="Negative_Correlation")], kb)
    db = tmp_path / "knowledge.sqlite"
    assert ingest_records(db, records)["added"] == 2
    query = query_database(db)
    assert query["relation_count"] == 2
    assert query["cross_document_entity_count"] == 3
    assert {r["doc_id"] for r in query["relations"]} == {"p1", "p2"}
    validation = validate_database(db)
    assert validation["structural_passed"] is True
    assert validation["scientific_review_complete"] is False
    assert len(validation["cross_document_label_differences"]) == 1
    assert ingest_records(db, records)["unchanged"] == 2
    assert query_database(db)["relation_count"] == 2


@pytest.mark.parametrize("corruption", ["span", "endpoint", "evidence", "duplicate_id"])
def test_invalid_records_are_rejected_before_persistence(tmp_path, kb, corruption):
    record = align_records([make_record()], kb)[0]
    if corruption == "span":
        record["entities"][0]["start"] += 1
    elif corruption == "endpoint":
        record["relations"][0]["head"] = "missing"
    elif corruption == "evidence":
        record["relations"][0]["evidence"][0]["text"] = "fabricated evidence"
    else:
        record["entities"][1]["mention_id"] = "e1"
    db = tmp_path / "knowledge.sqlite"
    with pytest.raises(ValueError):
        ingest_records(db, [record])
    assert not db.exists()


def test_changed_import_requires_revision_and_batch_rolls_back(tmp_path, kb):
    record = align_records([make_record()], kb)[0]
    db = tmp_path / "knowledge.sqlite"
    ingest_records(db, [record])
    other = deepcopy(record)
    other["doc_id"] = "new"
    changed = deepcopy(record)
    changed["relations"][0]["type"] = "Bind"
    with pytest.raises(ValueError, match="revise"):
        ingest_records(db, [other, changed])
    assert query_database(db)["doc_ids"] == ["p1"]


def test_revision_history_queries_and_incremental_import(tmp_path, kb):
    record = align_records([make_record()], kb)[0]
    db = tmp_path / "knowledge.sqlite"
    ingest_records(db, [record])
    broken = deepcopy(record)
    broken["relations"][0]["type"] = "Negative_Correlation"
    result = apply_revision(db, {"doc_id": "p1", "expected_version": 1, "replacement": broken,
                                "actor": "test", "reason": "known teaching perturbation",
                                "kind": "teaching_injection"})
    assert result["version"] == 2
    assert query_database(db)["relation_type_counts"] == {"Negative_Correlation": 1}
    correction = {"doc_id": "p1", "expected_version": 2, "replacement": record,
                  "actor": "test", "reason": "restore explicitly injected error",
                  "evidence": record["relations"][0]["evidence"]}
    apply_revision(db, correction)
    assert query_database(db)["relation_type_counts"] == {"Association": 1}
    assert [item["kind"] for item in history(db)] == ["import", "teaching_injection", "correction"]
    assert history(db)[1]["record"]["relations"][0]["type"] == "Negative_Correlation"
    with pytest.raises(ValueError, match="expected_version"):
        apply_revision(db, correction)
    new = deepcopy(record)
    new["doc_id"] = "p2"
    ingest_records(db, [new])
    assert query_database(db)["documents"] == 2
    assert query_database(db)["cross_document_entity_count"] == 3


def test_revision_requires_real_quote_and_fixed_source(tmp_path, kb):
    record = align_records([make_record()], kb)[0]
    db = tmp_path / "knowledge.sqlite"
    ingest_records(db, [record])
    revision = {"doc_id": "p1", "expected_version": 1, "replacement": record,
                "actor": "test", "reason": "test correction", "evidence": []}
    with pytest.raises(ValueError, match="证据"):
        apply_revision(db, revision)
    revision["evidence"] = [{"start": 0, "end": 2, "text": "XX"}]
    with pytest.raises(ValueError, match="证据"):
        apply_revision(db, revision)
    assert len(history(db)) == 1


def test_evaluation_counts_unresolved_relations_and_separates_gold(tmp_path, kb):
    record = align_records([make_record()], kb)[0]
    gold = deepcopy(record)
    for entity in gold["entities"]:
        entity["ids"] = entity.pop("links")
        entity["type"] = {"GeneOrGeneProduct": "Gene", "DiseaseOrPhenotypicFeature": "Disease", "OrganismTaxon": "Species"}[entity["type"]]
    gold["relations"] = [{"relation_id": "g1", "head_ids": [{"namespace": "NCBIGene", "id": "7157"}],
                          "tail_ids": [{"namespace": "MESH", "id": "D009369"}], "type": "Association", "novelty": "Novel"}]
    held_out = deepcopy(gold)
    held_out["doc_id"] = "held_out"
    path = tmp_path / "gold.jsonl"
    path.write_text(json.dumps(gold) + "\n" + json.dumps(held_out), encoding="utf-8")
    report = evaluate_records([record], path)
    assert report["ner_strict"]["f1"] == 1
    assert report["relation_end_to_end"]["f1"] == 1
    assert report["reference_documents_not_submitted"] == 1
    assert report["evidence_sentence_score"] is None
    record["entities"][0]["links"] = []
    report = evaluate_records([record], path)
    assert report["relation_end_to_end"]["predicted"] == 1
    assert report["relation_end_to_end"]["true_positive"] == 0


def test_retriever_preserves_quote_offsets_and_excludes_source():
    documents = [{"doc_id": "p1", "text": "Title\nTP53 regulates growth. Another observation."},
                 {"doc_id": "p2", "text": "TP53 has a role in cancer."}]
    result = retrieve_evidence(documents, "TP53 cancer", exclude_doc_id="p1")
    assert result and result[0]["doc_id"] == "p2"
    for item in result:
        source = next(d["text"] for d in documents if d["doc_id"] == item["doc_id"])
        assert source[item["start"]:item["end"]] == item["text"]
        assert item["status"] == "retrieved_candidate"


def test_species_plural_and_compound_mentions_use_explicit_words(tmp_path, kb):
    terms = [json.loads(line) for line in kb.read_text().splitlines()]
    terms[-1]["aliases"] = ["human"]
    kb.write_text("\n".join(json.dumps(term) for term in terms), encoding="utf-8")
    aligned = align_records([make_record()], kb)[0]
    assert aligned["entities"][0]["links"][0]["id"] == "7157"
    assert aligned["entities"][2]["links"][0]["id"] == "9606"


def test_document_abbreviation_has_traceable_source_and_no_gold(tmp_path):
    text = "Gestational diabetes mellitus (GDM) is studied. GDM is common."
    entities = []
    for n, (surface, start) in enumerate([("Gestational diabetes mellitus", 0),
                                         ("GDM", text.index("GDM")),
                                         ("GDM", text.rindex("GDM"))]):
        entities.append({"mention_id": f"e{n}", "text": surface, "start": start,
                         "end": start + len(surface), "type": "Disease"})
    term = {"namespace": "MESH", "id": "D016640", "name": "Gestational diabetes mellitus",
            "aliases": [], "type": "Disease", "source": "external-test-kb"}
    kb = tmp_path / "abbreviation.jsonl"
    kb.write_text(json.dumps(term), encoding="utf-8")
    aligned = align_records([{"doc_id": "abbr", "text": text, "entities": entities, "relations": []}], kb)[0]
    for entity in aligned["entities"][1:]:
        assert entity["links"][0]["id"] == "D016640"
        assert entity["links"][0]["method"] == "document_abbreviation"
        evidence = entity["abbreviation_evidence"]
        assert text[evidence["start"]:evidence["end"]] == evidence["text"]


def test_gene_symbol_plural_is_not_silently_singularized(tmp_path):
    text = "CATS"
    kb = tmp_path / "gene.jsonl"
    kb.write_text(json.dumps({"namespace": "NCBIGene", "id": "847", "name": "CAT", "aliases": [], "type": "Gene", "source": "test"}), encoding="utf-8")
    result = align_records([{"doc_id": "gene", "text": text, "entities": [{"mention_id": "e1", "text": text, "start": 0, "end": 4, "type": "Gene"}], "relations": []}], kb)[0]
    assert result["entities"][0]["link_status"] == "unresolved"


def test_resolved_model_candidate_still_requires_semantic_review(tmp_path, kb):
    record = align_records([make_record()], kb)[0]
    record["entities"][0]["link_review_status"] = "model_candidate"
    record["relations"] = []
    db = tmp_path / "candidate.sqlite"
    ingest_records(db, [record])
    validation = validate_database(db)
    assert validation["structural_passed"] is True
    assert validation["scientific_review_complete"] is False
    assert any(x["kind"] == "entity_link_semantics" for x in validation["pending_review"])


def test_document_species_does_not_assign_every_gene(kb):
    record = make_record(text="In humans, TP53 is associated with cancer.")
    result = align_records([record], kb)[0]
    assert result["entities"][0]["link_status"] == "ambiguous"
    assert result["entities"][0]["links"] == []
    assert "taxon_context" not in result["entities"][0]


@pytest.mark.parametrize("status,expected", [("unresolved", "resolved"), ("ambiguous", "ambiguous")])
def test_abbreviation_can_override_nonexhaustive_semantic_candidates(status, expected):
    text = "Gestational diabetes mellitus (GDM)."
    source = {"mention_id": "e1", "text": "Gestational diabetes mellitus", "start": 0,
              "end": 29, "type": "Disease", "link_status": "resolved",
              "links": [{"namespace": "MESH", "id": "D016640", "method": "external_alias", "score": 1.0}]}
    target = {"mention_id": "e2", "text": "GDM", "start": text.index("GDM"),
              "end": text.index("GDM") + 3, "type": "Disease", "link_status": status, "links": [],
              "link_candidates": [{"namespace": "MESH", "id": "D000001", "method": "sapbert_shortlist" if status == "unresolved" else "external_alias", "score": .5}]}
    record = {"doc_id": "abbr", "text": text, "entities": [source, target], "relations": []}
    _propagate_document_abbreviations(record)
    assert target["link_status"] == expected
    if expected == "resolved":
        assert target["links"][0]["id"] == "D016640"
        assert target["links"][0]["method"] == "document_abbreviation"
    else:
        assert target["links"] == []
