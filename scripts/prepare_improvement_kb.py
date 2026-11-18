#!/usr/bin/env python3
"""Prepare a separate rule-lab KB from frozen external sources, never gold.

Students use the bundled result. This maintainer command needs the original
gene_info downloads already checked into the local download cache.
"""
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bio_knowledge_lab.extraction import extract_document
from bio_knowledge_lab.improvement import normalize_gene_alias
from bio_knowledge_lab.io import read_jsonl, write_json, write_jsonl
from prepare_data import gene_entries


def main():
    data = ROOT / "data"
    manifest = json.loads((data / "manifest.json").read_text(encoding="utf-8"))
    sources = [s for s in manifest["sources"] if s["file"].endswith(".gene_info.gz")]
    for source in sources:
        path = data / "downloads" / source["file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError("Frozen source mismatch: " + source["file"])
    records = [extract_document(d, mode="replay") for d in read_jsonl(data / "corpus/documents.jsonl")]
    names = {e["text"] for d in records for e in d["entities"] if e["type"] == "GeneOrGeneProduct"}
    by_normal = {}
    for name in sorted(names):
        by_normal.setdefault(normalize_gene_alias(name), []).append(name)
    terms = {(t["namespace"], str(t["id"]), t["type"]): t for t in read_jsonl(data / "kb/entities.jsonl")}
    additions = 0
    for entry in gene_entries():
        matches = set()
        weak = set()
        for alias in entry["aliases"]:
            matches.update(by_normal.get(normalize_gene_alias(alias), []))
            # A long final word is a retrieval lead, not a claim of synonymy.
            # E.g. 'apoptosis inhibitor survivin' can retrieve 'survivin'.
            words = re.findall(r"[a-zA-Z0-9]+", alias)
            if len(words) > 1 and len(words[-1]) >= 6:
                weak.update(by_normal.get(normalize_gene_alias(words[-1]), []))
        if not matches and not weak:
            continue
        entry["retrieval_aliases"] = sorted(weak - matches)
        entry["candidate_selection"] = "predicted_name_normalized_or_long_suffix_retrieval"
        key = (entry["namespace"], str(entry["id"]), entry["type"])
        additions += key not in terms
        terms[key] = entry
    output = data / "improvement/entities.jsonl"
    write_jsonl(output, [terms[k] for k in sorted(terms)])
    artifacts = [output, data / "improvement/cell_context.json"]
    write_json(data / "improvement/manifest.json", {
        "schema_version": "1.0", "gene_snapshot_date": "2026-11-12",
        "built_date": "2026-11-18", "selection_uses_gold": False,
        "selection": "All predicted Gene names from the frozen 50-document replay; all matching species retained.",
        "suffix_matches_are_candidates_not_confirmed_synonyms": True,
        "base_candidate_count": 7347, "candidate_count": len(terms), "additional_entries": additions,
        "sources": sources,
        "artifacts": [{"path": str(p.relative_to(ROOT)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in artifacts],
    })
    print(json.dumps({"candidate_count": len(terms), "additional_entries": additions}))


if __name__ == "__main__":
    main()
