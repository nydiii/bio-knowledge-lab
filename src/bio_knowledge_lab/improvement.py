"""Offline, mention-level linking experiment; not a replacement for expert review.

Only independent dictionary entries and the supplied source text are read. The
previous model response is an input to compare with, not a response to a new
prompt. Entity extraction and relation labels remain unchanged.
"""
from collections import defaultdict
from copy import deepcopy
import json
from pathlib import Path
import re
import unicodedata

from .io import read_jsonl
from .pipeline import _abbreviation_compatible, _identifier, _type


GREEK = dict(zip("αβγδεζηθικλμνξοπρστυφχψω",
                 ("alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta",
                  "theta", "iota", "kappa", "lambda", "mu", "nu", "xi", "omicron",
                  "pi", "rho", "sigma", "tau", "upsilon", "phi", "chi", "psi", "omega")))
SPECIES = {"human": "9606", "humans": "9606", "mouse": "10090", "mice": "10090",
           "murine": "10090", "rat": "10116", "rats": "10116"}


def normalize_gene_alias(text):
    """Equate typography, retaining digits, Greek identity and other symbols."""
    text = unicodedata.normalize("NFKC", text).casefold()
    text = "".join(GREEK.get(character, character) for character in text)
    return re.sub(r"[\s\-‐‑‒–—]+", "", text)


def _spans(text):
    start = 0
    result = []
    for match in re.finditer(r"[.!?](?=\s|$)|[;\n]", text):
        end = match.end()
        if text[start:end].strip():
            result.append((start, end))
        start = end
    if text[start:].strip():
        result.append((start, len(text)))
    return result


def _quote(text, start, end):
    return {"start": start, "end": end, "text": text[start:end]}


def _cell_pattern(alias):
    letters = re.sub(r"[\s\-‐‑‒–—]", "", alias)
    return re.compile(r"(?<!\w)" + r"[\s\-‐‑‒–—]*".join(map(re.escape, letters)) + r"(?!\w)", re.I)


def _context(text, entity, spans, cell_patterns):
    index = next((i for i, (a, b) in enumerate(spans)
                  if a <= entity["start"] and entity["end"] <= b), None)
    if index is None:
        return {"taxa": set(), "basis": "no_local_context", "evidence": []}
    a, b = spans[index]
    sentence = text[a:b]
    local = _quote(text, a, b)
    before = text[max(a, entity["start"] - 45):entity["start"]]
    adjacent = re.search(r"\b(human|humans|mouse|mice|murine|rat|rats)\s+$", before, re.I)
    if adjacent:
        return {"taxa": {SPECIES[adjacent.group(1).lower()]},
                "basis": "explicit_mention_species", "evidence": [local]}

    # Bind application verbs to this mention, rather than treating a cell's
    # species as the provenance of a protein supplied to those cells.
    after = text[entity["end"]:b]
    dose = r"(?:\(?\s*\d+(?:\.\d+)?\s*[A-Za-zµμ]+(?:/[A-Za-z]+)?\s*\)?\s*)?"
    applied = (re.match(r"[\s-]*(stimulated|treated|induced|activated)\b", after, re.I)
               or re.search(r"\b(exogenous|recombinant|treatment with|addition of|administration of|injection of)\s*$", before, re.I)
               or re.search(r"\b(?:treated|stimulated|incubated|supplemented|challenged|exposed)\s+(?:with|to)\s+" + dose + r"$", before, re.I)
               or re.match(r"\s*" + dose + r"(?:(?:protein|peptide|ligand)\s+)?(?:(?:was|were|is|are|has been|had been)\s+)?"
                           r"(?:(?:directly|exogenously|subsequently)\s+)?(?:added|administered|applied|injected|supplied|introduced|infused)\b", after, re.I))
    taxa = {SPECIES[m.group().lower()] for m in re.finditer(r"\b(?:human|humans|mouse|mice|murine|rat|rats)\b", sentence, re.I)}
    cells = [(cell, match) for cell, pattern in cell_patterns for match in pattern.finditer(sentence)]
    if applied:
        return {"taxa": set(), "observed_taxa": taxa | {str(c["tax_id"]) for c, _ in cells},
                "basis": "applied_reagent_species_unproven", "evidence": [local]}
    if re.search(r"\b(host|recipient|stroma|stromal)\b", sentence, re.I):
        return {"taxa": set(), "observed_taxa": taxa | {str(c["tax_id"]) for c, _ in cells},
                "basis": "host_or_recipient_source_unproven", "evidence": [local]}
    if cells:
        cell_taxa = {str(cell["tax_id"]) for cell, _ in cells}
        # Mixed cells are not resolved by preferring the first name. A named
        # donor is bound to the gene only by an explicit expression construction;
        # being earlier in the sentence than 'xenograft' is not such evidence.
        host = re.search(r"\b(xenograft\w*|transplant\w*)\b", sentence, re.I)
        donor_expression = host and any(
            match.end() <= entity["start"] - a and re.fullmatch(
                r"\s+cells?\s+(?:that\s+)?(?:expressing|express|expressed|overexpressing)\s+",
                sentence[match.end():entity["start"] - a], re.I)
            for _, match in cells)
        combined = cell_taxa if donor_expression else cell_taxa | taxa
        return {"taxa": combined, "basis": "local_cell_origin",
                "evidence": [local], "cell_sources": sorted({cell["source_url"] for cell, _ in cells})}
    if taxa:
        # Hosts and subjects elsewhere in a sentence do not establish gene origin.
        return {"taxa": set(), "observed_taxa": taxa, "basis": "species_without_mention_binding", "evidence": [local]}

    # Carry a named cell experiment into its immediately following sentence only.
    # No title, summary, intervening species or document-wide majority shortcut.
    if index and not re.search(r"\b(conclusion|current study|overall|in vivo|xenograft\w*|other experiments?|another experiment)\b", sentence, re.I):
        pa, pb = spans[index - 1]
        previous = text[pa:pb]
        previous_cells = [cell for cell, pattern in cell_patterns if pattern.search(previous)]
        previous_taxa = {SPECIES[m.group().lower()] for m in re.finditer(r"\b(?:human|humans|mouse|mice|murine|rat|rats)\b", previous, re.I)}
        cell_taxa = {str(cell["tax_id"]) for cell in previous_cells}
        if (len(cell_taxa) == 1 and not (previous_taxa - cell_taxa) and b - pa <= 1100
                and not re.search(r"\b(host|recipient|stromal|xenograft\w*|transplant\w*)\b", previous, re.I)):
            return {"taxa": cell_taxa, "basis": "adjacent_cell_experiment",
                    "evidence": [_quote(text, pa, pb), local],
                    "cell_sources": sorted({cell["source_url"] for cell in previous_cells})}
    return {"taxa": set(), "basis": "no_local_species", "evidence": [local]}


def _aliases(record):
    aliases = defaultdict(set)
    for parenthesis in re.finditer(r"\(([^()\n]{2,64})\)", record["text"]):
        short = parenthesis.group(1).strip()
        for entity in record["entities"]:
            if _type(entity["type"]) != "Gene" or not 0 <= parenthesis.start() - entity["end"] <= 2:
                continue
            if record["text"][entity["end"]:parenthesis.start()].strip() or not _abbreviation_compatible(short, entity["text"]):
                continue
            long_key, short_key = map(normalize_gene_alias, (entity["text"], short))
            aliases[long_key].add(short_key)
            aliases[short_key].add(long_key)
    return aliases


def _link(term):
    return {"namespace": str(term["namespace"]), "id": str(term["id"]),
            "name": term.get("name", ""), "tax_id": term.get("tax_id"),
            "source": term.get("source"), "method": "mention_context_rule", "score": None}


def improve_records(records, kb_path, cell_context_path):
    """Reconsider supported local cases, leaving other baseline predictions intact.

    A new candidate, ambiguity or rule match is not human scientific confirmation.
    The function reads only its two supplied independent resource files.
    """
    index = defaultdict(dict)
    match_kinds = defaultdict(set)
    for term in read_jsonl(kb_path):
        if _type(term["type"]) == "Gene":
            for alias in [term["name"]] + term.get("aliases", []):
                key = normalize_gene_alias(alias)
                index[key][_identifier(term)] = term
                match_kinds[(key, _identifier(term))].add("official_alias_typography")
            for alias in term.get("retrieval_aliases", []):
                key = normalize_gene_alias(alias)
                index[key][_identifier(term)] = term
                match_kinds[(key, _identifier(term))].add("weak_descriptor_retrieval")
    cells = json.loads(Path(cell_context_path).read_text(encoding="utf-8"))["cells"]
    cell_patterns = [(cell, _cell_pattern(alias)) for cell in cells
                     for alias in dict.fromkeys([cell["name"]] + cell.get("aliases", []))]
    output = deepcopy(records)
    for record in output:
        spans, aliases = _spans(record["text"]), _aliases(record)
        contexts = {entity["mention_id"]: _context(record["text"], entity, spans, cell_patterns)
                    for entity in record["entities"] if _type(entity["type"]) == "Gene"}
        grouped_taxa = defaultdict(set)
        for entity in record["entities"]:
            if entity["mention_id"] in contexts:
                context = contexts[entity["mention_id"]]
                grouped_taxa[normalize_gene_alias(entity["text"])].update(context["taxa"] | context.get("observed_taxa", set()))
        for entity in record["entities"]:
            if _type(entity["type"]) != "Gene":
                continue
            old_links = deepcopy(entity.get("links", []))
            context = contexts[entity["mention_id"]]
            key = normalize_gene_alias(entity["text"])
            candidate_map = {identifier: term for form in {key} | aliases[key]
                             for identifier, term in index.get(form, {}).items()}
            candidates = [candidate_map[k] for k in sorted(candidate_map)]
            old_ids = {_identifier(link) for link in old_links}
            taxa = context["taxa"]
            rule_only = any(link.get("method") in {"external_alias", "document_abbreviation"} for link in old_links)
            new_conflict = rule_only and len(candidate_map) > 1 and bool(set(candidate_map) - old_ids)
            mixed_group = len(grouped_taxa[key]) > 1 and any(link.get("method") == "contextual_candidate_selection" for link in old_links)
            source_unproven = context["basis"] in {"applied_reagent_species_unproven", "host_or_recipient_source_unproven"}
            triggered = bool(taxa) or new_conflict or mixed_group or source_unproven
            review = {"status": "not_rechecked", "reason": "本轮规则没有充分局部依据，保留旧版候选。",
                      "context_basis": context["basis"], "evidence": context["evidence"],
                      "cell_sources": context.get("cell_sources", [])}
            entity["improvement_review"] = review
            if not triggered:
                continue
            if not old_links:
                # A source species alone does not turn an unresolved family or
                # ambiguous subtype into a specific gene. This experiment audits
                # existing assignments rather than expanding that uncertain set.
                review["reason"] = "旧版尚未确定具体基因；局部物种不能单独确认家族成员或亚型，本轮保留原状态。"
                continue
            compatible = [term for term in candidates if str(term.get("tax_id")) in taxa] if taxa else []
            old_taxa = {str(link["tax_id"]) for link in old_links if link.get("tax_id")}
            review["previous_links"] = old_links
            review["previous_link_status"] = entity.get("link_status", "unresolved")
            review["candidate_match_basis"] = [
                {"namespace": identifier[0], "id": identifier[1], "basis": sorted(set().union(
                    *(match_kinds[(form, identifier)] for form in {key} | aliases[key])))}
                for identifier in sorted(candidate_map)]
            if len(taxa) == 1 and len(compatible) == 1:
                entity.update(links=[_link(compatible[0])], link_status="resolved", link_candidates=[],
                              link_review_status="rule_candidate", link_reason="独立别名候选与本次提及的局部来源一致。")
                entity["link_evidence"] = context["evidence"][-1]
                review.update(status="rule_candidate", reason=entity["link_reason"])
            else:
                reason = ("局部物种对应多个基因或亚型，不能选择唯一身份。" if len(compatible) > 1 else
                          "局部来源与候选物种不相容。" if len(taxa) == 1 else
                          "同名候选或不同实验涉及多个物种，当前提及缺少唯一身份依据。")
                if len(taxa) == 1 and old_taxa and not (taxa & old_taxa):
                    # Positive evidence contradicts the old assignment's species.
                    entity.update(links=[], link_status="ambiguous" if candidates else "unresolved",
                                  link_candidates=[_link(term) for term in compatible or candidates],
                                  link_review_status="pending", link_reason=reason)
                    entity.pop("link_evidence", None)
                else:
                    # More candidates or missing local evidence does not prove
                    # the existing assignment wrong. Retain it as a pending
                    # baseline candidate, not as a newly validated prediction.
                    reason += " 保留旧版候选并提示待核查，本轮未确认或修复该身份。"
                    entity.update(link_review_status="pending", link_reason=reason)
                review.update(status="needs_review", reason=reason)
            entity.pop("abbreviation_evidence", None)
        record["improvement"] = {"method": "offline_mention_context_rules", "gold_used": False,
                                 "new_model_calls": 0, "extraction_changed": False, "relation_labels_changed": False}
    return output
