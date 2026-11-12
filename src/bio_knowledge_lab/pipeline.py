"""CPU knowledge modelling. Gold labels are read only by evaluate_records.

Lexical linking is a course baseline. The optional SapBERT route adapts MDKG's
embedding similarity step after a lexical shortlist; it is not full MDKG.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from difflib import SequenceMatcher
import hashlib
import itertools
import json
from pathlib import Path
import re
import sqlite3
import unicodedata


TYPE_MAP = {
    "GeneOrGeneProduct": "Gene", "DiseaseOrPhenotypicFeature": "Disease",
    "ChemicalEntity": "Chemical", "SequenceVariant": "Variant",
    "OrganismTaxon": "Species", "CellLine": "CellLine",
    "Gene": "Gene", "Disease": "Disease", "Chemical": "Chemical",
    "Variant": "Variant", "Species": "Species",
}
RELATION_TYPES = {"Association", "Positive_Correlation", "Negative_Correlation",
                  "Bind", "Comparison", "Conversion", "Cotreatment",
                  "Drug_Interaction"}


def _read_jsonl(path):
    with Path(path).open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _now():
    return datetime.now(timezone.utc).isoformat()


def _norm(text):
    # Preserve hyphens, digits, Greek letters and other identity-bearing symbols.
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _type(value):
    return TYPE_MAP.get(value, value)


def _lookup_forms(text, kind):
    """Conservative grammatical variants; never strip characters from gene symbols."""
    value = _norm(text)
    forms = [value]
    if kind in {"Species", "Disease", "Chemical"}:
        if value.endswith("ies") and len(value) > 5:
            forms.append(value[:-3] + "y")
        elif value.endswith("s") and not value.endswith(("ss", "us", "is")) and len(value) > 3:
            forms.append(value[:-1])
    if kind == "Species":
        forms.append({"mice": "mouse", "humans": "human"}.get(value, value))
        # Explicit species descriptors inside mentions such as 'nude mice'.
        # Anatomical names alone ('pancreas') never supply species identity.
        for match in re.finditer(r"\b(humans?|mice|mouse|rats?)\b", value):
            token = match.group()
            forms.append({"humans": "human", "mice": "mouse", "rats": "rat"}.get(token, token))
    return list(dict.fromkeys(forms))


def _abbreviation_compatible(short, long):
    """A conservative backwards character alignment, anchored at a word start."""
    short = re.sub(r"[^\w]", "", _norm(short))
    long = _norm(long)
    if not 2 <= len(short) <= 12 or len(short) >= len(re.sub(r"\W", "", long)):
        return False
    cursor = len(long) - 1
    for position in range(len(short) - 1, -1, -1):
        character = short[position]
        while cursor >= 0 and (long[cursor] != character or
                               (position == 0 and cursor and long[cursor - 1].isalnum())):
            cursor -= 1
        if cursor < 0:
            return False
        cursor -= 1
    return True


def _propagate_document_abbreviations(record):
    """Link short forms using explicit long-form (short-form) evidence only.

    This is course adaptation of MDKG's context-based abbreviation resolution.
    Existing disagreeing candidate identities are preserved for review.
    """
    entities = record.get("entities", [])
    text = record.get("text", "")
    aliases = []
    for parenthesis in re.finditer(r"\(([^()\n]{2,64})\)", text):
        short = parenthesis.group(1).strip()
        for entity in entities:
            if entity["end"] > parenthesis.start() or parenthesis.start() - entity["end"] > 2:
                continue
            if text[entity["end"]:parenthesis.start()].strip():
                continue
            if not _abbreviation_compatible(short, entity["text"]):
                continue
            aliases.append((_type(entity["type"]), entity["text"], short,
                            {"start": entity["start"], "end": parenthesis.end(),
                             "text": text[entity["start"]:parenthesis.end()]}))
    for kind, long, short, evidence in aliases:
        for source_name, target_name in ((long, short), (short, long)):
            source_entities = [e for e in entities if _type(e["type"]) == kind and
                               set(_lookup_forms(e["text"], kind)) & set(_lookup_forms(source_name, kind))]
            source_links = {_identifier(link): link for e in source_entities for link in e.get("links", [])}
            # Different identities for the same surface in the document are not
            # safe to propagate without explicit mention-level disambiguation.
            if len(source_links) != 1:
                continue
            key, link = next(iter(source_links.items()))
            for target in entities:
                if _type(target["type"]) != kind or target.get("link_status") == "resolved":
                    continue
                if not set(_lookup_forms(target["text"], kind)) & set(_lookup_forms(target_name, kind)):
                    continue
                candidate_ids = {_identifier(value) for value in target.get("link_candidates", [])}
                # Exact alias ambiguity defines an identity conflict. A truncated
                # semantic retrieval list is not exhaustive negative evidence.
                if target.get("link_status") == "ambiguous" and candidate_ids and key not in candidate_ids:
                    continue
                target.update(link_status="resolved", links=[{**deepcopy(link), "method": "document_abbreviation",
                              "abbreviation_evidence": evidence}], abbreviation_evidence=evidence)


def _adjacent_taxon(record, entity, species_index):
    """Use only an immediately preceding species qualifier, never a whole paper.

    'human TP53' is explicit; a mouse elsewhere in a xenograft paper does not
    establish the organism of its genes. Unrecognized context remains unresolved.
    """
    start = entity.get("start", 0)
    source = record.get("text", "")
    if not start or not source[start - 1].isspace():
        return None
    prefix = " " + _norm(source[max(0, start - 64):start])
    matches = set()
    for alias, terms in species_index.items():
        variants = [alias]
        if alias in {"human", "rat"}:
            variants.append(alias + "s")
        if alias == "mouse":
            variants.append("mice")
        if any(prefix.endswith(" " + variant) for variant in variants):
            matches.update(str(term.get("tax_id") or term["id"]) for term in terms)
    return next(iter(matches)) if len(matches) == 1 else None


def _identifier(value):
    return str(value["namespace"]), str(value["id"])


def _id_set(entity):
    values = entity.get("ids", entity.get("links", []))
    return frozenset(_identifier(value) for value in values if value.get("namespace") and value.get("id"))


def _link(term, method, score):
    return {"namespace": str(term["namespace"]), "id": str(term["id"]),
            "name": term.get("name", ""), "tax_id": term.get("tax_id"),
            "source": term.get("source"), "method": method, "score": round(float(score), 6)}


class _SapBERT:
    """Load optional dependencies only when this route is explicitly selected."""
    def __init__(self):
        try:
            import torch
            from transformers import AutoTokenizer, AutoModel
        except ImportError as error:
            raise RuntimeError("SapBERT需要安装可选依赖：pip install -e '.[semantic]'；免费lexical路径不需要。") from error
        import os
        self.torch = torch
        self.model_name = os.environ.get("BIO_LAB_SAPBERT_MODEL", "cambridgeltl/SapBERT-from-PubMedBERT-fulltext")
        options = {} if Path(self.model_name).is_dir() else {"revision": "090663c3ae57bf35ffe4d0d468a2a88d03051a4d"}
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name, **options)
        self.model = AutoModel.from_pretrained(self.model_name, **options).to("cpu").eval()
        self.cache = {}

    def embeddings(self, strings):
        missing = list(dict.fromkeys(s for s in strings if s not in self.cache))
        for begin in range(0, len(missing), 32):
            batch = missing[begin:begin + 32]
            inputs = self.tokenizer(batch, padding=True, truncation=True, max_length=64, return_tensors="pt")
            with self.torch.no_grad():
                hidden = self.model(**inputs).last_hidden_state
                mask = inputs["attention_mask"].unsqueeze(-1)
                vectors = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1)
                vectors = self.torch.nn.functional.normalize(vectors, dim=1)
            for term, vector in zip(batch, vectors):
                self.cache[term] = vector
        return self.torch.stack([self.cache[term] for term in strings])

    def rerank(self, mention, candidates):
        names = [term["name"] for term in candidates]
        vectors = self.embeddings([mention] + names)
        scores = (vectors[1:] @ vectors[0]).tolist()
        return sorted(zip(candidates, scores), key=lambda item: (-item[1], _identifier(item[0])))


def align_records(records, kb_path, method="lexical"):
    """Resolve unambiguous external aliases; never consult reference annotations.

    Ambiguous aliases remain unresolved. SapBERT scores are similarity scores,
    not scientific confidence. The optional route accepts >=.88 similarity
    only with >=.05 margin over a different candidate and compatible taxon.
    """
    if method not in {"lexical", "sapbert"}:
        raise ValueError("method必须为lexical或sapbert")
    kb = _read_jsonl(kb_path)
    index, token_index, length_index = (defaultdict(list) for _ in range(3))
    kb_hash = hashlib.sha256(Path(kb_path).read_bytes()).hexdigest()
    for term in kb:
        entity_type = _type(term["type"])
        length_index[(entity_type, len(_norm(term["name"])))].append(term)
        for token in set(re.findall(r"\w+", _norm(term["name"]))):
            token_index[(entity_type, token)].append(term)
        for name in set([term["name"]] + term.get("aliases", [])):
            if name:
                index[(entity_type, _norm(name))].append(term)
    model = None
    resolved_cache = {}
    output = deepcopy(list(records))
    species_index = {name: terms for (kind, name), terms in index.items() if kind == "Species"}
    for record in output:
        for entity in record.get("entities", []):
            kind, name = _type(entity["type"]), entity["text"]
            # A model-supplied tax_id is not used as authoritative context.
            taxon = _adjacent_taxon(record, entity, species_index) if kind == "Gene" else None
            cache_key = (kind, name, taxon, method)
            if cache_key not in resolved_cache:
                terms = {_identifier(t): t for form in _lookup_forms(name, kind) for t in index.get((kind, form), [])}
                # Explicit species context can exclude incompatible identifiers,
                # but missing taxon metadata cannot prove compatibility.
                if taxon:
                    terms = {key: term for key, term in terms.items() if str(term.get("tax_id")) == taxon}
                if len(terms) == 1:
                    value = {"link_status": "resolved", "links": [_link(next(iter(terms.values())), "external_alias", 1.0)], "link_candidates": []}
                elif terms:
                    value = {"link_status": "ambiguous", "links": [], "link_candidates": [_link(t, "external_alias", 1.0) for t in terms.values()]}
                else:
                    value = {"link_status": "unresolved", "links": [], "link_candidates": []}
                    if method == "sapbert":
                        # Bound expensive string comparison to an inverted-index
                        # shortlist. With no token overlap use nearby name lengths;
                        # this is a course speed adaptation, not full-KB retrieval.
                        pooled = {}
                        for token in set(re.findall(r"\w+", _norm(name))):
                            for term in token_index.get((kind, token), []):
                                pooled[_identifier(term)] = term
                        if not pooled:
                            for width in range(max(1, len(_norm(name)) - 2), len(_norm(name)) + 3):
                                for term in length_index.get((kind, width), []):
                                    pooled[_identifier(term)] = term
                        pool = list(pooled.values())
                        if taxon:
                            pool = [term for term in pool if str(term.get("tax_id")) == taxon]
                        # An explicit ceiling prevents pathological broad terms
                        # from scanning an entire large terminology repeatedly.
                        pool = sorted(pool, key=lambda t: (abs(len(_norm(t["name"])) - len(_norm(name))), _identifier(t)))[:512]
                        shortlist = sorted(pool, key=lambda t: SequenceMatcher(None, _norm(name), _norm(t["name"])).ratio(), reverse=True)[:32]
                        if shortlist:
                            if model is None:
                                model = _SapBERT()
                            ranked = model.rerank(name, shortlist)
                            # Collapse synonyms duplicated across external KB rows.
                            distinct = {}
                            for term, score in ranked:
                                distinct.setdefault(_identifier(term), (term, score))
                            ranked = list(distinct.values())
                            value["link_candidates"] = [_link(t, "sapbert_shortlist", s) for t, s in ranked[:5]]
                            best, score = ranked[0]
                            margin = score - ranked[1][1] if len(ranked) > 1 else 1.0
                            # Gene identity requires a known species for semantic
                            # fallback; generic gene names alone are insufficient.
                            if score >= .88 and margin >= .05 and (kind != "Gene" or taxon):
                                value["link_status"] = "resolved"
                                value["links"] = [_link(best, "sapbert_shortlist", score)]
                if taxon:
                    value["taxon_context"] = {"tax_id": taxon, "basis": "explicit_adjacent_species_qualifier"}
                resolved_cache[cache_key] = value
            entity.update(deepcopy(resolved_cache[cache_key]))
        _propagate_document_abbreviations(record)
        record["alignment"] = {"method": method, "kb_sha256": kb_hash,
                               "gold_used": False, "unresolved_policy": "preserve", "semantic_threshold": .88 if method == "sapbert" else None,
                               "semantic_candidates": "token overlap or name length ±2; cap512 then top32 string similarity" if method == "sapbert" else None}
    return output


def _record_issues(record):
    errors, warnings = [], []
    doc_id = record.get("doc_id")
    if not isinstance(doc_id, str) or not doc_id:
        errors.append("doc_id必须为非空字符串")
    text = record.get("text")
    if not isinstance(text, str) or not text:
        errors.append("必须携带未经修改的原文text以验证跨度")
        text = ""
    mentions = {}
    for entity in record.get("entities", []):
        mid = entity.get("mention_id")
        if not isinstance(mid, str) or not mid or mid in mentions:
            errors.append(f"实体mention_id为空或重复: {mid}")
        mentions[mid] = entity
        start, end = entity.get("start"), entity.get("end")
        if not (type(start) is int and type(end) is int and 0 <= start < end <= len(text)):
            errors.append(f"实体跨度无效: {mid}")
        elif text[start:end] != entity.get("text"):
            errors.append(f"实体文本与原文跨度不一致: {mid}")
        if _type(entity.get("type")) not in set(TYPE_MAP.values()):
            warnings.append(f"未定义实体类型: {mid}/{entity.get('type')}")
        links = entity.get("links", [])
        for link in links:
            if not link.get("namespace") or not link.get("id"):
                errors.append(f"实体标识缺少namespace/id: {mid}")
        if entity.get("link_status") == "ambiguous" and links:
            errors.append(f"歧义实体不可静默选择标准标识: {mid}")
    relation_ids = set()
    for rel in record.get("relations", []):
        rid = rel.get("relation_id")
        if not rid or rid in relation_ids:
            errors.append(f"关系relation_id为空或重复: {rid}")
        relation_ids.add(rid)
        if rel.get("head") not in mentions or rel.get("tail") not in mentions:
            errors.append(f"关系端点不存在: {rid}")
        if rel.get("head") == rel.get("tail"):
            warnings.append(f"关系两端为同一提及，需核查: {rid}")
        if rel.get("type") not in RELATION_TYPES:
            warnings.append(f"未定义关系类型: {rid}/{rel.get('type')}")
        if rel.get("direction") not in (None, "unknown", "undirected", "not_annotated") and not rel.get("direction_source"):
            warnings.append(f"方向没有标注来源: {rid}")
        if not rel.get("evidence"):
            warnings.append(f"尚无候选证据跨度: {rid}")
        for evidence in rel.get("evidence", []):
            start, end = evidence.get("start"), evidence.get("end")
            if not (type(start) is int and type(end) is int and 0 <= start < end <= len(text)):
                errors.append(f"证据跨度无效: {rid}")
            elif text[start:end] != evidence.get("text"):
                errors.append(f"证据文本与原文不一致: {rid}")
    return errors, warnings


def _connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            doc_id TEXT PRIMARY KEY, text TEXT NOT NULL, current_version INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS snapshots (
            doc_id TEXT NOT NULL, version INTEGER NOT NULL, record_json TEXT NOT NULL,
            record_hash TEXT NOT NULL, created_at TEXT NOT NULL, kind TEXT NOT NULL,
            reason TEXT NOT NULL, actor TEXT NOT NULL, evidence_json TEXT NOT NULL,
            PRIMARY KEY(doc_id,version), FOREIGN KEY(doc_id) REFERENCES documents(doc_id));
        CREATE TABLE IF NOT EXISTS mentions (
            doc_id TEXT NOT NULL, mention_id TEXT NOT NULL, content_json TEXT NOT NULL,
            PRIMARY KEY(doc_id,mention_id), FOREIGN KEY(doc_id) REFERENCES documents(doc_id));
        CREATE TABLE IF NOT EXISTS entity_links (
            doc_id TEXT NOT NULL, mention_id TEXT NOT NULL, namespace TEXT NOT NULL,
            entity_id TEXT NOT NULL, content_json TEXT NOT NULL,
            PRIMARY KEY(doc_id,mention_id,namespace,entity_id),
            FOREIGN KEY(doc_id,mention_id) REFERENCES mentions(doc_id,mention_id));
        CREATE TABLE IF NOT EXISTS relations (
            doc_id TEXT NOT NULL, relation_id TEXT NOT NULL, content_json TEXT NOT NULL,
            PRIMARY KEY(doc_id,relation_id), FOREIGN KEY(doc_id) REFERENCES documents(doc_id));
        CREATE INDEX IF NOT EXISTS links_by_entity ON entity_links(namespace,entity_id);
    """)
    return connection


def _materialize(connection, record):
    doc_id = record["doc_id"]
    for table in ("entity_links", "mentions", "relations"):
        connection.execute(f"DELETE FROM {table} WHERE doc_id=?", (doc_id,))
    for entity in record.get("entities", []):
        connection.execute("INSERT INTO mentions VALUES(?,?,?)", (doc_id, entity["mention_id"], _json(entity)))
        for link in entity.get("links", []):
            connection.execute("INSERT INTO entity_links VALUES(?,?,?,?,?)", (doc_id, entity["mention_id"], str(link["namespace"]), str(link["id"]), _json(link)))
    for rel in record.get("relations", []):
        connection.execute("INSERT INTO relations VALUES(?,?,?)", (doc_id, rel["relation_id"], _json(rel)))


def ingest_records(db_path, records):
    records = list(records)
    for record in records:
        errors, _ = _record_issues(record)
        if errors:
            raise ValueError(f"拒绝导入 {record.get('doc_id')}: {'; '.join(errors)}")
    added, unchanged = [], []
    with _connect(db_path) as connection:
        for record in records:
            doc_id, payload = record["doc_id"], _json(record)
            digest = hashlib.sha256(payload.encode()).hexdigest()
            old = connection.execute("SELECT s.record_hash FROM documents d JOIN snapshots s ON d.doc_id=s.doc_id AND d.current_version=s.version WHERE d.doc_id=?", (doc_id,)).fetchone()
            if old:
                if old["record_hash"] != digest:
                    raise ValueError(f"文献 {doc_id} 已存在且内容改变；必须通过revise保留历史。")
                unchanged.append(doc_id)
                continue
            connection.execute("INSERT INTO documents VALUES(?,?,1)", (doc_id, record["text"]))
            connection.execute("INSERT INTO snapshots VALUES(?,?,?,?,?,?,?,?,?)", (doc_id, 1, payload, digest, _now(), "import", "initial or incremental import", "pipeline", "[]"))
            _materialize(connection, record)
            added.append(doc_id)
    return {"added": len(added), "unchanged": len(unchanged), "added_doc_ids": added, "unchanged_doc_ids": unchanged}


def current_records(db_path):
    """Return current snapshots; this is the input for validation and querying."""
    if not Path(db_path).is_file():
        raise FileNotFoundError(f"知识库不存在: {db_path}")
    with _connect(db_path) as connection:
        rows = connection.execute("SELECT s.record_json FROM snapshots s JOIN documents d ON d.doc_id=s.doc_id AND d.current_version=s.version ORDER BY d.doc_id").fetchall()
    return [json.loads(row[0]) for row in rows]


def query_database(db_path):
    records = current_records(db_path)
    groups = defaultdict(lambda: {"documents": set(), "aliases": set(), "mentions": 0})
    statuses, relation_types = Counter(), Counter()
    relations = []
    for record in records:
        entities = {e["mention_id"]: e for e in record.get("entities", [])}
        for entity in entities.values():
            statuses[entity.get("link_status", "unresolved")] += 1
            for link in entity.get("links", []):
                group = groups[_identifier(link)]
                group["documents"].add(record["doc_id"])
                group["aliases"].add(entity["text"])
                group["mentions"] += 1
        for rel in record.get("relations", []):
            relation_types[rel["type"]] += 1
            head, tail = entities.get(rel["head"], {}), entities.get(rel["tail"], {})
            relations.append({"doc_id": record["doc_id"], **deepcopy(rel),
                              "head_text": head.get("text"), "tail_text": tail.get("text"),
                              "head_ids": head.get("links", []), "tail_ids": tail.get("links", []),
                              "scientific_review_status": rel.get("scientific_review_status", "pending")})
    shared = [{"namespace": key[0], "id": key[1], "doc_ids": sorted(value["documents"]),
               "aliases": sorted(value["aliases"]), "mention_count": value["mentions"]}
              for key, value in sorted(groups.items()) if len(value["documents"]) > 1]
    with _connect(db_path) as connection:
        versions = {row["doc_id"]: row["current_version"] for row in connection.execute("SELECT * FROM documents")}
    return {"documents": len(records), "doc_ids": [r["doc_id"] for r in records],
            "entity_mentions": sum(len(r.get("entities", [])) for r in records),
            "canonical_entities": len(groups), "link_status_counts": dict(statuses),
            "relation_count": len(relations), "relation_type_counts": dict(relation_types),
            "cross_document_entity_count": len(shared), "cross_document_entities": shared,
            "versions": versions, "relations": relations}


def validate_database(db_path):
    errors, warnings, pending = [], [], []
    for record in current_records(db_path):
        local_errors, local_warnings = _record_issues(record)
        errors.extend({"doc_id": record["doc_id"], "message": message} for message in local_errors)
        warnings.extend({"doc_id": record["doc_id"], "message": message} for message in local_warnings)
        for entity in record.get("entities", []):
            if entity.get("link_status") != "resolved":
                pending.append({"doc_id": record["doc_id"], "kind": "entity_link", "record_id": entity["mention_id"], "text": entity["text"], "status": entity.get("link_status", "unresolved")})
            elif entity.get("link_review_status") == "model_candidate":
                pending.append({"doc_id": record["doc_id"], "kind": "entity_link_semantics", "record_id": entity["mention_id"], "text": entity["text"], "status": "model_candidate"})
        for rel in record.get("relations", []):
            if rel.get("scientific_review_status") != "human_confirmed":
                pending.append({"doc_id": record["doc_id"], "kind": "relation_semantics", "record_id": rel["relation_id"], "status": "pending"})
    query = query_database(db_path)
    by_pair = defaultdict(list)
    for rel in query["relations"]:
        for pair in itertools.product(rel["head_ids"], rel["tail_ids"]):
            key = tuple(sorted(_identifier(value) for value in pair))
            by_pair[key].append(rel)
    differences = []
    for pair, rels in by_pair.items():
        if len({r["doc_id"] for r in rels}) > 1 and len({r["type"] for r in rels}) > 1:
            differences.append({"entity_pair": pair, "observations": [{"doc_id": r["doc_id"], "relation_id": r["relation_id"], "type": r["type"], "novelty": r.get("novelty"), "context": r.get("context", {})} for r in rels],
                                "status": "different_labels_require_context_review_not_automatic_error"})
    return {"passed": not errors, "structural_passed": not errors, "scientific_review_complete": not pending,
            "errors": errors, "warnings": warnings, "pending_review": pending,
            "cross_document_label_differences": differences,
            "note": "跨度及结构通过不代表科学语义正确；关系与证据句仍需参考/人工核查。"}


def apply_revision(db_path, revision):
    """Replace one current document snapshot with optimistic version control."""
    if not Path(db_path).is_file():
        raise FileNotFoundError(db_path)
    doc_id = revision["doc_id"]
    replacement = deepcopy(revision["replacement"])
    if replacement.get("doc_id") != doc_id:
        raise ValueError("修订不能改变文献doc_id")
    if not revision.get("reason") or not revision.get("actor"):
        raise ValueError("修订必须有reason和actor")
    kind = revision.get("kind", "correction")
    if kind not in {"correction", "teaching_injection"}:
        raise ValueError("修订kind必须为correction或teaching_injection")
    if kind == "correction" and not revision.get("evidence"):
        raise ValueError("修订必须提供原文证据；教学错误必须明确标记teaching_injection")
    errors, _ = _record_issues(replacement)
    if errors:
        raise ValueError("拒绝无效修订: " + "; ".join(errors))
    with _connect(db_path) as connection:
        row = connection.execute("SELECT * FROM documents WHERE doc_id=?", (doc_id,)).fetchone()
        if row is None:
            raise ValueError("不能修订不存在的文献")
        if type(revision.get("expected_version")) is not int or revision["expected_version"] != row["current_version"]:
            raise ValueError("expected_version已过期；请重新查看当前版本")
        if replacement.get("text") != row["text"]:
            raise ValueError("不能修改固定原文；原文版本更新需要独立来源记录")
        for evidence in revision.get("evidence", []):
            start, end = evidence.get("start"), evidence.get("end")
            if not (type(start) is int and type(end) is int and 0 <= start < end <= len(row["text"]) and row["text"][start:end] == evidence.get("text")):
                raise ValueError("修订证据与原文不一致")
        version = row["current_version"] + 1
        payload = _json(replacement)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        connection.execute("INSERT INTO snapshots VALUES(?,?,?,?,?,?,?,?,?)", (doc_id, version, payload, digest, _now(), kind, revision["reason"], revision["actor"], _json(revision.get("evidence", []))))
        connection.execute("UPDATE documents SET current_version=? WHERE doc_id=? AND current_version=?", (version, doc_id, revision["expected_version"]))
        _materialize(connection, replacement)
    return {"doc_id": doc_id, "previous_version": version - 1, "version": version, "kind": kind, "record_hash": digest}


def history(db_path):
    if not Path(db_path).is_file():
        raise FileNotFoundError(db_path)
    with _connect(db_path) as connection:
        rows = connection.execute("SELECT * FROM snapshots ORDER BY doc_id,version").fetchall()
    return [{"doc_id": row["doc_id"], "version": row["version"], "created_at": row["created_at"],
             "kind": row["kind"], "reason": row["reason"], "actor": row["actor"],
             "evidence": json.loads(row["evidence_json"]), "record_hash": row["record_hash"],
             "record": json.loads(row["record_json"])} for row in rows]


def _metric(predicted, gold):
    true_positive = len(predicted & gold)
    precision = true_positive / len(predicted) if predicted else 0.0
    recall = true_positive / len(gold) if gold else 0.0
    return {"true_positive": true_positive, "predicted": len(predicted), "gold": len(gold),
            "precision": precision, "recall": recall, "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0}


def _relation_keys(record, gold=False, with_novelty=False):
    entities = {entity["mention_id"]: entity for entity in record.get("entities", [])}
    keys = set()
    for relation in record.get("relations", []):
        if gold and "head_ids" in relation:
            head = [_identifier(x) for x in relation["head_ids"]]
            tail = [_identifier(x) for x in relation["tail_ids"]]
        else:
            head = list(_id_set(entities.get(relation.get("head"), {})))
            tail = list(_id_set(entities.get(relation.get("tail"), {})))
        # Unresolved predictions count as false positives, rather than vanish.
        head = head or [("UNRESOLVED", str(relation.get("head", relation.get("relation_id"))))]
        tail = tail or [("UNRESOLVED", str(relation.get("tail", relation.get("relation_id"))))]
        for left, right in itertools.product(head, tail):
            key = (record["doc_id"], tuple(sorted((left, right))), relation["type"])
            if with_novelty:
                key += (relation.get("novelty", "Unknown"),)
            keys.add(key)
    return keys


def evaluate_records(records, gold_path):
    """Gold-only evaluation; do not pass this data into extract/align.

    Scores cover submitted documents only, allowing initial and incremental
    stages to be evaluated separately without treating held-out papers as FN.
    """
    records = list(records)
    references = {record["doc_id"]: record for record in _read_jsonl(gold_path)}
    submitted = {record["doc_id"] for record in records}
    gold = [references[key] for key in sorted(submitted & references.keys())]
    def mention_keys(items, linked=False):
        keys = set()
        for record in items:
            for entity in record.get("entities", []):
                key = (record["doc_id"], entity["start"], entity["end"], _type(entity["type"]))
                if linked:
                    ids = _id_set(entity)
                    if not ids:
                        continue
                    key += (tuple(sorted(ids)),)
                keys.add(key)
        return keys
    p_rel = set().union(*[_relation_keys(r) for r in records]) if records else set()
    g_rel = set().union(*[_relation_keys(r, gold=True) for r in gold]) if gold else set()
    p_novel = set().union(*[_relation_keys(r, with_novelty=True) for r in records]) if records else set()
    g_novel = set().union(*[_relation_keys(r, gold=True, with_novelty=True) for r in gold]) if gold else set()
    return {"evaluated_documents": len(gold), "submitted_documents": len(submitted),
            "documents_without_gold": sorted(submitted - references.keys()),
            "reference_documents_not_submitted": len(references.keys() - submitted),
            "ner_strict": _metric(mention_keys(records), mention_keys(gold)),
            "linking_strict": _metric(mention_keys(records, True), mention_keys(gold, True)),
            "relation_end_to_end": _metric(p_rel, g_rel),
            "relation_with_novelty": _metric(p_novel, g_novel),
            "evidence_sentence_score": None, "context_score": None,
            "evaluation_notes": ["实体严格比较原文跨度和类型；链接还需标准标识集合一致。", "原BioRED无方向关系按无序标准实体对、标签和文档评价。", "未解决端点的预测关系计入预测分母。", "没有逐句证据/上下文金标，不给出伪造分数。", "金标未进入实体对齐或模型输入。"]}
