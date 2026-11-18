"""Synthetic sentence contrasts exercise rule scope, not biological gold."""
from copy import deepcopy
import re

import pytest

from bio_knowledge_lab.relation_rules import improve_relation_evidence


def record(text, first="ABC1", second="DEF2", relation_type="Positive_Correlation"):
    entities = []
    for surface in (first, second):
        for match in re.finditer(re.escape(surface), text):
            entities.append({"mention_id": f"m{len(entities)+1}", "text": surface,
                             "type": "GeneOrGeneProduct", "start": match.start(), "end": match.end()})
    # Use the last occurrence as endpoint: earlier mentions still supply a
    # document-level candidate, without inventing an alias correspondence.
    endpoints = [next(e for e in reversed(entities) if e["text"] == name)["mention_id"] for name in (first, second)]
    return {"doc_id": "synthetic", "text": text, "entities": entities,
            "relations": [{"relation_id": "r1", "head": endpoints[0], "tail": endpoints[1],
                           "type": relation_type, "novelty": "Novel", "evidence": [],
                           "evidence_status": "model_candidate", "direction": "not_annotated"}]}


def result(source):
    return improve_relation_evidence([source])[0]["relations"][0]


def test_knockdown_expression_uses_full_sentence_and_preserves_input():
    source = record("Title\nConsistent with impaired growth, ABC1 knockdown increased levels of the kinase inhibitors DEF2 and GHI3. ABC1 and DEF2 were studied.")
    before = deepcopy(source)
    relation = result(source)
    assert source == before
    assert relation["type"] == "Negative_Correlation"
    assert relation["relation_rule_review"]["original_type"] == "Positive_Correlation"
    assert relation["relation_rule_review"]["status"] == "rule_candidate"
    assert relation["relation_rule_review"]["gold_used"] is False
    assert relation["evidence_status"] == "rule_candidate"
    assert relation["direction"] == "not_annotated"
    for quote in relation["evidence"]:
        assert source["text"][quote["start"]:quote["end"]] == quote["text"]
        assert quote["text"].startswith("Consistent with") and quote["text"].endswith(".")


def test_passive_repression_matches_alias_parenthesis_and_either_endpoint_order():
    source = record("Expression analysis reveals that factor DEF2 (DEF2/DF) is transcriptionally repressed by ABC1, especially in cells cultured in serum-free medium. ABC1 affects DEF2.")
    relation = result(source)
    assert relation["type"] == "Negative_Correlation"
    source["relations"][0]["head"], source["relations"][0]["tail"] = source["relations"][0]["tail"], source["relations"][0]["head"]
    assert result(source)["type"] == "Negative_Correlation"
    alias = record("Factor alpha (FA/DEF2) is transcriptionally repressed by ABC1.")
    assert result(alias)["type"] == "Negative_Correlation"


@pytest.mark.parametrize("controller_object", [
    "ABC1 inhibitor", "ABC1 inhibitors", "ABC1 antagonist", "ABC1 antagonists",
    "ABC1 activator", "ABC1 activators", "ABC1 receptor", "ABC1 receptors",
    "ABC1 antibodies", "(ABC1) inhibitors", "(ABC1) antagonists", "(ABC1) receptors",
])
def test_controller_modifier_is_not_mistaken_for_the_controller(controller_object):
    source = record(f"DEF2 is transcriptionally repressed by {controller_object}.")
    relation = result(source)
    assert relation["type"] == "Positive_Correlation"
    assert relation["evidence"] == []
    assert relation["evidence_status"] == "model_candidate"
    review = relation["relation_rule_review"]
    assert review["status"] == "needs_review"
    assert review["reason"] == "ambiguous_controller_object"
    assert review["proposed_type"] is None
    assert review["original_type"] == "Positive_Correlation"
    assert review["evidence"][0]["text"] == source["text"]
    quote = review["evidence"][0]
    assert source["text"][quote["start"]:quote["end"]] == quote["text"]


@pytest.mark.parametrize("text", [
    "ABC1 knockdown did not increase levels of DEF2.",
    "Without treatment, ABC1 knockdown increased levels of DEF2.",
    "No evidence showed ABC1 knockdown increased levels of DEF2.",
    "DEF2 is not transcriptionally repressed by ABC1.",
    "ABC1 knockdown increased the number of DEF2(+) cells.",
    "ABC1 knockdown increased levels of DEF2-positive cells.",
    "ABC1 knockdown increased levels of DEF2 inhibitors GHI3.",
    "ABC1 knockdown increased levels of a kinase (DEF2) inhibitor GHI3.",
    "ABC1 knockdown increased levels of inhibitors of DEF2.",
    "ABC1 knockdown increased growth, whereas DEF2 decreased.",
    "ABC1 knockdown increased expression of a factor that activates DEF2.",
    "Other knockdown and ABC1 knockdown increased levels of DEF2.",
    "Other and ABC1 knockdown increased levels of DEF2.",
    "DEF2 is transcriptionally repressed by ABC1 and Another.",
    "ABC1 knockdown increased DEF2 after treatment with another compound.",
    "ABC1 inhibits the effects of a drug on DEF2.",
])
def test_unsafe_or_unrecognized_sentences_leave_original_unchanged(text):
    source = record(text)
    assert result(source) == source["relations"][0]


@pytest.mark.parametrize("opposing", [
    "ABC1 knockdown decreased levels of DEF2.",
    "DEF2 is transcriptionally activated by ABC1.",
    "ABC1 activates DEF2.",
])
def test_opposing_source_patterns_retain_original_and_flag_review(opposing):
    source = record("ABC1 knockdown increased levels of DEF2. " + opposing)
    relation = result(source)
    assert relation["type"] == "Positive_Correlation"
    assert relation["evidence"] == []
    assert relation["evidence_status"] == "model_candidate"
    assert relation["relation_rule_review"]["status"] == "needs_review"
    assert relation["relation_rule_review"]["reason"] == "conflicting_sentence_patterns"


@pytest.mark.parametrize("label", ["Association", "Bind", "Comparison"])
def test_other_relation_categories_are_not_replaced(label):
    source = record("DEF2 is transcriptionally repressed by ABC1.", relation_type=label)
    assert result(source) == source["relations"][0]


def test_existing_negative_is_only_annotated_and_rerunning_is_idempotent():
    source = record("ABC1 knockdown increased DEF2.", relation_type="Negative_Correlation")
    once = improve_relation_evidence([source])
    assert once[0]["relations"][0]["type"] == "Negative_Correlation"
    assert once[0]["relations"][0]["relation_rule_review"]["original_type"] == "Negative_Correlation"
    assert once[0]["relations"][0]["evidence"] == source["relations"][0]["evidence"]
    assert once[0]["relations"][0]["evidence_status"] == "model_candidate"
    assert improve_relation_evidence(once) == once


def test_unmentioned_names_and_non_gene_targets_are_not_used():
    source = record("ABC1 knockdown increased levels of DEF2.")
    source["entities"][1]["type"] = "CellLine"
    assert result(source) == source["relations"][0]
    source = record("ABC1 and DEF2 were studied. ABC1 knockdown increased levels of DEF2.")
    source["entities"] = [e for e in source["entities"] if e["start"] < 20]
    source["relations"][0]["head"] = source["entities"][0]["mention_id"]
    source["relations"][0]["tail"] = source["entities"][1]["mention_id"]
    assert result(source) == source["relations"][0]


def test_same_name_with_a_different_standard_identity_is_not_merged():
    source = record("ABC1 knockdown increased DEF2. ABC1 and DEF2 were studied.")
    first_occurrence = next(e for e in source["entities"] if e["text"] == "ABC1")
    last_occurrence = next(e for e in reversed(source["entities"]) if e["text"] == "ABC1")
    first_occurrence["links"] = [{"namespace": "NCBIGene", "id": "11"}]
    last_occurrence["links"] = [{"namespace": "NCBIGene", "id": "22"}]
    assert result(source) == source["relations"][0]
