"""Counterexamples for the offline teaching improvement; fixtures are synthetic."""
from copy import deepcopy
import json
import re

import pytest

from bio_knowledge_lab.improvement import improve_records, normalize_gene_alias


def term(identifier, tax_id, aliases=None):
    return {"namespace": "NCBIGene", "id": identifier, "name": "ABC1",
            "aliases": aliases or [], "type": "Gene", "tax_id": tax_id, "source": "synthetic-external-kb"}


def record(text, surface="ABC1", method="contextual_candidate_selection"):
    entities = []
    for i, match in enumerate(re.finditer(re.escape(surface), text)):
        entities.append({"mention_id": f"m{i}", "text": surface, "start": match.start(), "end": match.end(),
                         "type": "GeneOrGeneProduct", "link_status": "resolved",
                         "links": [{"namespace": "NCBIGene", "id": "human", "tax_id": "9606", "method": method}]})
    return {"doc_id": "synthetic", "text": text, "entities": entities,
            "relations": [{"relation_id": "r1", "type": "Association", "head": "m0", "tail": "m0"}]}


@pytest.fixture
def resources(tmp_path):
    kb = tmp_path / "kb.jsonl"
    kb.write_text("\n".join(json.dumps(t) for t in [term("human", "9606"), term("mouse", "10090")]), encoding="utf-8")
    cells = tmp_path / "cells.json"
    cells.write_text(json.dumps({"cells": [{"name": "H-CELL", "aliases": [], "tax_id": "9606", "source_url": "https://example.org/human"},
                                           {"name": "M-CELL", "aliases": [], "tax_id": "10090", "source_url": "https://example.org/mouse"}]}), encoding="utf-8")
    return kb, cells


def test_local_mentions_can_have_different_species(resources):
    source = record("Human ABC1 rises. Mouse ABC1 falls.")
    result = improve_records([source], *resources)[0]
    assert [e["links"][0]["id"] for e in result["entities"]] == ["human", "mouse"]
    assert all(e["link_review_status"] == "rule_candidate" for e in result["entities"])


def test_cell_origin_is_not_xenograft_host(resources):
    source = record("H-CELL cells expressing ABC1 formed xenografts in mice.")
    source["entities"][0]["links"][0].update(id="mouse", tax_id="10090", method="external_alias")
    result = improve_records([source], *resources)[0]["entities"][0]
    assert result["links"][0]["id"] == "human"
    assert result["improvement_review"]["cell_sources"] == ["https://example.org/human"]


def test_reagent_species_is_not_implied_by_cells(resources):
    source = record("H-CELL cells underwent ABC1-stimulated uptake.", method="external_alias")
    result = improve_records([source], *resources)[0]["entities"][0]
    assert result["links"] == source["entities"][0]["links"]
    assert result["link_review_status"] == "pending"
    assert result["improvement_review"]["context_basis"] == "applied_reagent_species_unproven"


@pytest.mark.parametrize("text", [
    "ABC1 was added to H-CELL cells.",
    "H-CELL cells were stimulated with ABC1.",
    "H-CELL cells were exposed to ABC1.",
    "ABC1 protein was administered to H-CELL cells.",
    "ABC1 was directly injected into H-CELL cells.",
    "Addition of ABC1 altered H-CELL cells.",
    "H-CELL cells were stimulated with 10 nM ABC1.",
    "ABC1 (10 ng/ml) was added to H-CELL cells.",
])
def test_applied_protein_is_bound_to_application_phrase(resources, text):
    source = record(text)
    source["entities"][0]["links"][0].update(id="mouse", tax_id="10090")
    result = improve_records([source], *resources)[0]["entities"][0]
    assert result["links"] == source["entities"][0]["links"]
    assert result["link_review_status"] == "pending"
    assert result["improvement_review"]["context_basis"] == "applied_reagent_species_unproven"


def test_application_of_other_reagent_does_not_bind_to_gene_readout(resources):
    source = record("H-CELL cells were treated with a drug and ABC1 expression increased.")
    source["entities"][0]["links"][0].update(id="mouse", tax_id="10090")
    result = improve_records([source], *resources)[0]["entities"][0]
    assert result["links"][0]["id"] == "human"


@pytest.mark.parametrize("text", [
    "Host ABC1 was elevated after H-CELL xenografts grew in mice.",
    "Recipient ABC1 increased after H-CELL cells were transplanted into mice.",
    "ABC1 increased before H-CELL xenografts grew in mice.",
])
def test_gene_before_xenograft_word_does_not_prove_donor_origin(resources, text):
    source = record(text)
    source["entities"][0]["links"][0].update(id="mouse", tax_id="10090")
    result = improve_records([source], *resources)[0]["entities"][0]
    assert result["links"] == source["entities"][0]["links"]
    assert result["link_review_status"] == "pending"


def test_host_readout_after_transplant_is_not_assumed_to_be_donor(resources):
    source = record("H-CELL cells formed xenografts in mice and host ABC1 increased.")
    result = improve_records([source], *resources)[0]["entities"][0]
    assert result["links"] == source["entities"][0]["links"]
    assert result["improvement_review"]["status"] == "needs_review"


def test_new_alias_ambiguity_flags_without_claiming_old_prediction_wrong(resources):
    source = record("ABC1 is involved in growth.", method="external_alias")
    result = improve_records([source], *resources)[0]["entities"][0]
    assert result["links"] == source["entities"][0]["links"]
    assert result["link_review_status"] == "pending"
    assert result["improvement_review"]["status"] == "needs_review"


def test_no_new_evidence_preserves_model_baseline(resources):
    source = record("ABC1 is involved in growth.")
    result = improve_records([source], *resources)[0]["entities"][0]
    assert result["links"] == source["entities"][0]["links"]
    assert result["improvement_review"]["status"] == "not_rechecked"


def test_mixed_cell_context_does_not_pick_first(resources):
    source = record("H-CELL and M-CELL cells express ABC1.")
    result = improve_records([source], *resources)[0]["entities"][0]
    assert result["links"] == source["entities"][0]["links"]
    assert result["improvement_review"]["status"] == "needs_review"


def test_alias_normalization_keeps_identity_bearing_characters():
    assert normalize_gene_alias("GSK-3 β") == normalize_gene_alias("GSK-3beta")
    assert normalize_gene_alias("ABC 1") != normalize_gene_alias("ABC 2")
    assert normalize_gene_alias("ABCα") != normalize_gene_alias("ABCβ")
    assert normalize_gene_alias("A/B") != normalize_gene_alias("AB")


def test_weak_descriptor_hit_requires_local_species(resources):
    kb, cells = resources
    entry = {**term("human", "9606"), "name": "Survival inhibitor ABC1", "retrieval_aliases": ["ABC1"]}
    kb.write_text(json.dumps(entry), encoding="utf-8")
    no_context = record("ABC1 affects growth.")
    no_context["entities"][0].update(links=[], link_status="unresolved")
    result = improve_records([no_context], kb, cells)[0]["entities"][0]
    assert result["links"] == []
    supported = improve_records([record("H-CELL cells express ABC1.")], kb, cells)[0]["entities"][0]
    assert supported["links"][0]["id"] == "human"
    assert supported["improvement_review"]["candidate_match_basis"][0]["basis"] == ["weak_descriptor_retrieval"]


def test_multiple_subtypes_in_same_species_remain_ambiguous(resources):
    kb, cells = resources
    with kb.open("a") as stream:
        stream.write("\n" + json.dumps(term("human_other_subtype", "9606")))
    source = record("Human ABC1 rises.")
    result = improve_records([source], kb, cells)[0]["entities"][0]
    assert result["links"] == source["entities"][0]["links"]
    assert result["link_review_status"] == "pending"


def test_explicit_incompatible_species_withdraws_old_id(resources):
    source = record("Rat ABC1 rises.")
    result = improve_records([source], *resources)[0]["entities"][0]
    assert result["links"] == []
    assert result["link_status"] == "ambiguous"
    assert result["link_review_status"] == "pending"


def test_cell_species_does_not_upgrade_unresolved_family(resources):
    source = record("H-CELL cells express ABC1 family proteins.")
    source["entities"][0].update(links=[], link_status="ambiguous")
    result = improve_records([source], *resources)[0]["entities"][0]
    assert result["links"] == []
    assert result["link_status"] == "ambiguous"


def test_improvement_does_not_mutate_or_read_references(resources, monkeypatch):
    source = record("H-CELL cells express ABC1.")
    snapshot = deepcopy(source)
    from pathlib import Path
    original_open = Path.open
    allowed = {resources[0].resolve(), resources[1].resolve()}
    def limited_open(path, *args, **kwargs):
        assert path.resolve() in allowed
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", limited_open)
    result = improve_records([source], *resources)[0]
    assert source == snapshot
    assert result["relations"] == snapshot["relations"]
    for before, after in zip(source["entities"], result["entities"]):
        assert {k: before[k] for k in ["mention_id", "text", "type", "start", "end"]} == {
            k: after[k] for k in ["mention_id", "text", "type", "start", "end"]}
        for quote in after["improvement_review"]["evidence"]:
            assert result["text"][quote["start"]:quote["end"]] == quote["text"]


def test_adjacent_experiment_does_not_cross_intervening_species(resources):
    source = record("H-CELL cells were examined. Mice received a treatment. ABC1 increased.")
    result = improve_records([source], *resources)[0]["entities"][0]
    assert result["improvement_review"]["status"] == "not_rechecked"


def test_explicit_abbreviation_shares_candidates_not_chosen_ids(resources):
    kb, cells = resources
    kb.write_text("\n".join(json.dumps({**t, "aliases": ["Alpha beta component 1"]})
                            for t in [term("human", "9606"), term("mouse", "10090")]), encoding="utf-8")
    text = "Alpha beta component 1 (ABC1) is examined. H-CELL cells express ABC1."
    source = record(text)
    source["entities"].insert(0, {"mention_id": "long", "text": "Alpha beta component 1", "start": 0,
                                  "end": len("Alpha beta component 1"), "type": "Gene", "links": [], "link_status": "unresolved"})
    result = improve_records([source], kb, cells)[0]
    assert result["entities"][-1]["links"][0]["id"] == "human"
    assert result["entities"][0]["links"] == []
