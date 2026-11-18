"""Narrow, source-only relation rules for the improvement lesson.

These patterns propose gene-expression correlations, not expert judgments or
general causal inference. They never read reference labels or call a model.
"""
from copy import deepcopy
import re


_GENE_TYPES = {"Gene", "GeneOrGeneProduct"}
_NEGATION = re.compile(r"\b(?:not|no|neither|nor|without|failed|fails|fail|absence)\b|n't\b", re.I)
_MIXED = re.compile(r"\b(?:but|whereas|while|although|however|unless|either)\b|;", re.I)
_INTERVENTION = re.compile(r"\b(?:knockdown|silencing|depletion|overexpression|knockout|treatment|stimulation)\b", re.I)
_CELL_QUANTITY = re.compile(r"\b(?:number|numbers|proportion|percentage|fraction|population|frequency|viability|proliferation)\b", re.I)
_ANOTHER_PREDICATE = re.compile(r"\b(?:which|that|whereas|through|via|increased|increases|reduced|reduces|decreased|decreases|activates|activated|inhibits|inhibited|repressed)\b", re.I)


def _sentences(text):
    # A line break or a sentence terminator starts a new evidence unit. Original
    # offsets are retained; fragments are never joined with an ellipsis.
    for match in re.finditer(r"[^.!?\n]+(?:[.!?]+|$)", text):
        raw = match.group()
        start = match.start() + len(raw) - len(raw.lstrip())
        end = match.end() - len(raw) + len(raw.rstrip())
        if start < end:
            yield {"start": start, "end": end, "text": text[start:end]}


def _word(surface):
    return r"(?<![\w-])" + re.escape(surface) + r"(?![\w-])"


def _safe(sentence):
    return not (_NEGATION.search(sentence) or _MIXED.search(sentence))


def _knockdown(sentence, controller, target):
    """Return a signed pattern only when target is in a simple expression object."""
    match = re.search(_word(controller) + r"\s+knockdown\s+(?:significantly\s+)?"
                      r"(?P<verb>increased|increases|decreased|decreases|reduced|reduces)\s+", sentence, re.I)
    if not match or len(_INTERVENTION.findall(sentence)) != 1:
        return None
    if re.search(r"\b(?:and|or|plus)\s*$", sentence[:match.start()], re.I):
        return None  # A combined knockdown cannot identify one controller.
    obj = sentence[match.end():]
    target_match = re.search(_word(target), obj, re.I)
    if not target_match or _CELL_QUANTITY.search(obj) or _ANOTHER_PREDICATE.search(obj) or "," in obj:
        return None
    if re.search(r"\(\s*[+-]\s*\)|[- ]positive\b|[- ]negative\b", obj, re.I):
        return None  # A marker-positive cell count is not marker expression.
    # Support the direct target, or an explicit level/expression object. Do not
    # infer a gene relationship from an arbitrary downstream phenotype.
    prefix = obj[:target_match.start()].strip()
    if prefix and not re.match(r"(?:the\s+)?(?:levels?|expression)\s+of\b", prefix, re.I):
        return None
    if re.search(r"\b(?:inhibitors?|activators?|antagonists?|agonists?)\s+(?:of|targeting)\b", prefix, re.I):
        return None
    if re.match(r"\)*\s*(?:inhibitors?|activators?|antagonists?|agonists?|receptors?|substrates?|targets?)\b", obj[target_match.end():], re.I):
        return None  # "Y inhibitors" measures the inhibitors, not Y itself.
    sign = "Negative_Correlation" if match["verb"].lower().startswith("increas") else "Positive_Correlation"
    return sign, "knockdown_expression"


def _transcription(sentence, controller, target):
    # Permit an explicit parenthesized alias after the full name, or the closing
    # parenthesis when the named target is itself the final alias in parentheses.
    match = re.search(_word(target) + r"(?:\s*\([^()\n]*\)|\))*\s+"
                      r"(?:is|are|was|were)\s+transcriptionally\s+"
                      r"(?P<verb>repressed|activated)\s+by\s+(?:\(\s*)?" + _word(controller), sentence, re.I)
    if not match or _INTERVENTION.search(sentence):
        return None
    suffix = sentence[match.end():]
    if re.match(r"\s*\)*\s*(?:inhibitors?|antagonists?|agonists?|activators?|receptors?|"
                r"substrates?|targets?|antibod(?:y|ies)|ligands?|mutants?)\b", suffix, re.I):
        # "by X inhibitors" names an intervention on X, not X itself. Neither
        # its effect nor the opposite correlation can be inferred by this rule.
        return None, "ambiguous_controller_object"
    if re.match(r"\s*\)*\s*(?:and\b|or\b|plus\b|[/&])", suffix, re.I):
        return None
    sign = "Negative_Correlation" if match["verb"].lower() == "repressed" else "Positive_Correlation"
    return sign, "explicit_transcription"


def _direct_positive(sentence, controller, target):
    # This is a conflict detector only: no positive label is written by the
    # lesson. A direct activation statement blocks a competing negative rule.
    pattern = (_word(controller) + r"\s+(?:directly\s+)?"
               r"(?:increases|increased|activates|activated|induces|induced|positively regulates)\s+"
               r"(?:(?:the\s+)?(?:expression|levels?)\s+of\s+)?" + _word(target))
    return ("Positive_Correlation", "opposing_activation") if re.search(pattern, sentence, re.I) else None


def _pair_evidence(record, first, second, sentences):
    names = {first["text"].casefold(), second["text"].casefold()}
    endpoint_ids = {e["text"].casefold(): {(i["namespace"], str(i["id"])) for i in e.get("links", [])}
                    for e in (first, second)}
    mentions = []
    for entity in record["entities"]:
        name = entity["text"].casefold()
        if entity["type"] not in _GENE_TYPES or name not in names:
            continue
        ids = {(i["namespace"], str(i["id"])) for i in entity.get("links", [])}
        if ids and endpoint_ids[name] and ids != endpoint_ids[name]:
            continue  # Same spelling with a different linked identity is not coreference.
        mentions.append(entity)
    found = []
    for sentence in sentences:
        present = {e["text"].casefold() for e in mentions
                   if sentence["start"] <= e["start"] < e["end"] <= sentence["end"]}
        if present != names or not _safe(sentence["text"]):
            continue
        for controller, target in ((first["text"], second["text"]), (second["text"], first["text"])):
            for rule in (_knockdown, _transcription, _direct_positive):
                result = rule(sentence["text"], controller, target)
                if result:
                    sign, name = result
                    item = {**sentence, "rule": name, "suggested_type": sign}
                    if item not in found:
                        found.append(item)
    return found


def improve_relation_evidence(records):
    """Return copied records with narrow, traceable negative-rule candidates.

    Only positive/negative correlation candidates are eligible. Other relation
    categories and unrecognized syntax remain unchanged. All same-name mentions
    in the document may provide evidence, because relations are document-level.
    """
    improved = deepcopy(list(records))
    for record in improved:
        entities = {e["mention_id"]: e for e in record["entities"]}
        sentences = list(_sentences(record["text"]))
        for relation in record["relations"]:
            if relation["type"] not in {"Positive_Correlation", "Negative_Correlation"}:
                continue
            if relation.get("relation_rule_review", {}).get("version") == 1:
                continue
            first, second = entities[relation["head"]], entities[relation["tail"]]
            if any(e["type"] not in _GENE_TYPES for e in (first, second)) or first["text"].casefold() == second["text"].casefold():
                continue
            evidence = _pair_evidence(record, first, second, sentences)
            negative = [e for e in evidence if e["suggested_type"] == "Negative_Correlation"]
            ambiguous_object = any(e["rule"] == "ambiguous_controller_object" for e in evidence)
            if not negative and not ambiguous_object:
                continue
            conflict = any(e["suggested_type"] != "Negative_Correlation" for e in evidence)
            relation["relation_rule_review"] = {
                "version": 1, "status": "needs_review" if conflict else "rule_candidate",
                "original_type": relation["type"], "original_evidence": deepcopy(relation.get("evidence", [])),
                "original_evidence_status": relation.get("evidence_status"),
                "proposed_type": "Negative_Correlation" if negative else None, "evidence": evidence,
                "reason": ("ambiguous_controller_object" if ambiguous_object else
                           "conflicting_sentence_patterns" if conflict else "explicit_expression_pattern"),
                "gold_used": False,
            }
            if not conflict and relation["type"] == "Positive_Correlation":
                relation["type"] = "Negative_Correlation"
                relation["evidence"] = [{k: e[k] for k in ("start", "end", "text")} for e in negative]
                relation["evidence_status"] = "rule_candidate"
                relation["relation_review_status"] = "rule_candidate"
    return improved
