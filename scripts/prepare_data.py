#!/usr/bin/env python3
"""Rebuild the teaching corpus and independent candidate KB (Python stdlib only).

Gold is used ONLY for corpus sampling and evaluation export. Candidate retrieval
uses unannotated document text and independent NCBI/NLM dictionaries.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from itertools import chain
from pathlib import Path
import re
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SOURCES = {
    "BIORED.zip": "https://ftp.ncbi.nlm.nih.gov/pub/lu/BioRED/BIORED.zip",
    "BioRED_Annotation_Guideline.pdf": "https://ftp.ncbi.nlm.nih.gov/pub/lu/BioRED/BioRED_Annotation_Guideline.pdf",
    **{f"{sp}.gene_info.gz": f"https://ftp.ncbi.nlm.nih.gov/gene/DATA/GENE_INFO/Mammalia/{sp}.gene_info.gz"
       for sp in ("Homo_sapiens", "Mus_musculus", "Rattus_norvegicus")},
    "desc2026.gz": "https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/desc2026.gz",
    "supp2026.gz": "https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/supp2026.gz",
    "taxonomy_9606_10090_10116.xml": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=taxonomy&id=9606,10090,10116&retmode=xml",
}
TYPE_NS = {"GeneOrGeneProduct": "NCBIGene", "OrganismTaxon": "NCBITaxon",
           "DiseaseOrPhenotypicFeature": "MESH", "ChemicalEntity": "MESH",
           "CellLine": "Cellosaurus", "SequenceVariant": "tmVar"}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n")


def fetch(refresh_lock=False):
    folder = DATA / "downloads"
    folder.mkdir(parents=True, exist_ok=True)
    old = json.loads((DATA / "manifest.json").read_text(encoding="utf-8")) if (DATA / "manifest.json").exists() else {}
    locks = {x["file"]: x["sha256"] for x in old.get("sources", [])}
    for name, url in SOURCES.items():
        path = folder / name
        if not path.exists():
            temporary = path.with_suffix(path.suffix + ".part")
            request = urllib.request.Request(url, headers={"User-Agent": "bio-knowledge-lab/0.1 educational corpus preparation"})
            with urllib.request.urlopen(request, timeout=240) as response, temporary.open("wb") as out:
                for chunk in iter(lambda: response.read(1024 * 1024), b""):
                    out.write(chunk)
            temporary.replace(path)
        if not refresh_lock and name in locks and sha(path) != locks[name]:
            raise ValueError(f"Upstream snapshot changed: {name}. Do not silently overwrite the bundled KB; use --verify-bundled for the frozen course data.")


def identifiers(raw, entity_type):
    values = []
    # Composite annotations can carry several identifiers separated by commas.
    for token in str(raw or "").split(","):
        token = token.strip()
        if token in ("", "-", "-1"):
            continue
        namespace = TYPE_NS[entity_type]
        if token.startswith("MESH:"):
            namespace, token = "MESH", token[5:]
        elif token.startswith("OMIM:"):
            namespace, token = "OMIM", token[5:]
        elif entity_type == "SequenceVariant" and token.startswith("rs"):
            namespace = "dbSNP"
        values.append({"namespace": namespace, "id": token})
    return values


def read_biored():
    records = []
    with zipfile.ZipFile(DATA / "downloads/BIORED.zip") as archive:
        for source_split in ("Train", "Dev", "Test"):
            payload = json.loads(archive.read(f"BioRED/{source_split}.BioC.JSON"))
            for doc in payload["documents"]:
                title, abstract = [p["text"] for p in doc["passages"]]
                text = title + "\n" + abstract
                entities, id_map = [], defaultdict(list)
                for passage in doc["passages"]:
                    # BioRED title + one separator + abstract offsets already
                    # coincide with our title + newline + abstract coordinate.
                    for a in passage.get("annotations", []):
                        locs = a["locations"]
                        if len(locs) != 1:
                            raise ValueError("Unexpected discontinuous annotation: " + doc["id"])
                        start = locs[0]["offset"]
                        end = start + locs[0]["length"]
                        if text[start:end] != a["text"]:
                            raise ValueError(f"Offset mismatch {doc['id']} annotation {a['id']}")
                        t = a["infons"]["type"]
                        ids = identifiers(a["infons"].get("identifier"), t)
                        mention = {"mention_id": "T" + str(a["id"]), "text": a["text"],
                                   "start": start, "end": end, "type": t, "ids": ids}
                        entities.append(mention)
                        for identifier in ids:
                            if identifier not in id_map[identifier["id"]]:
                                id_map[identifier["id"]].append(identifier)
                relations = []
                for r in doc.get("relations", []):
                    info = r["infons"]
                    def resolve(raw):
                        output = []
                        for token in raw.split(","):
                            for identifier in id_map.get(token, []):
                                if identifier not in output:
                                    output.append(identifier)
                        return output
                    relations.append({"relation_id": r["id"], "head_ids": resolve(info["entity1"]),
                                      "tail_ids": resolve(info["entity2"]), "type": info["type"],
                                      "novelty": info["novel"], "raw_head": info["entity1"],
                                      "raw_tail": info["entity2"], "direction": "not_annotated"})
                records.append({"doc_id": doc["id"], "title": title, "abstract": abstract,
                                "text": text, "source_split": source_split.lower(),
                                "entities": entities, "relations": relations})
    if len(records) != 600:
        raise ValueError(f"Expected original BioRED 600, found {len(records)}")
    return records


def connectivity_ids(record):
    return {f"{i['namespace']}:{i['id']}" for e in record["entities"]
            if e["type"] in ("GeneOrGeneProduct", "DiseaseOrPhenotypicFeature") for i in e["ids"]}


def select_documents(records, size=50):
    sets = {r["doc_id"]: connectivity_ids(r) for r in records}
    freq = Counter(k for ids in sets.values() for k in ids)
    useful = {k for k, n in freq.items() if 2 <= n <= 45}
    sets = {d: ids & useful for d, ids in sets.items()}
    pool = {r["doc_id"]: r for r in records}
    seed = max(pool, key=lambda d: (sum(math.log1p(freq[k]) for k in sorted(sets[d])), -int(d)))
    selected, coverage = [], Counter()
    next_id = seed
    while pool and len(selected) < size:
        r = pool.pop(next_id)
        selected.append(r)
        coverage.update(sets[next_id])
        if not pool:
            break
        def score(d):
            shared = sets[d] & coverage.keys()
            return (bool(shared), sum(min(coverage[k], 3) / math.sqrt(freq[k]) for k in sorted(shared)),
                    len(shared), len(sets[d]), -int(d))
        next_id = max(pool, key=score)
    for n, r in enumerate(selected):
        r["split"] = "incremental" if n % 5 == 4 else "initial"
    return selected


def normalized(text):
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def raw_queries(documents):
    queries = set()
    for d in documents:
        tokens = normalized(d["text"]).split()
        for width in range(1, 13):
            queries.update(" ".join(tokens[i:i + width]) for i in range(len(tokens) - width + 1))
    return queries


def gene_entries():
    for name in SOURCES:
        if not name.endswith(".gene_info.gz"):
            continue
        with gzip.open(DATA / "downloads" / name, "rt") as stream:
            for line in stream:
                if line.startswith("#"):
                    continue
                p = line.rstrip("\n").split("\t")
                aliases = set([p[2], p[8], p[10], p[11]] + p[4].split("|") + p[13].split("|")) - {"-", ""}
                yield {"namespace": "NCBIGene", "id": p[1], "name": p[2], "aliases": sorted(aliases),
                       "type": "GeneOrGeneProduct", "tax_id": p[0], "source": SOURCES[name],
                       "source_record_url": "https://www.ncbi.nlm.nih.gov/gene/" + p[1]}


def mesh_entries():
    descriptor_types = {}
    for filename, tag in (("desc2026.gz", "DescriptorRecord"), ("supp2026.gz", "SupplementalRecord")):
        with gzip.open(DATA / "downloads" / filename, "rb") as stream:
            iterator = ET.iterparse(stream, events=("start", "end"))
            _, root = next(iterator)
            for event, node in iterator:
                if event != "end" or node.tag != tag:
                    continue
                if tag == "DescriptorRecord":
                    uid = node.findtext("DescriptorUI")
                    name = node.findtext("DescriptorName/String")
                    trees = [x.text or "" for x in node.findall("TreeNumberList/TreeNumber")]
                    types = []
                    if any(t.startswith(("C", "F03")) for t in trees):
                        types.append("DiseaseOrPhenotypicFeature")
                    if any(t.startswith("D") for t in trees):
                        types.append("ChemicalEntity")
                    descriptor_types[uid] = types
                else:
                    uid = node.findtext("SupplementalRecordUI")
                    name = node.findtext("SupplementalRecordName/String")
                    types = sorted({t for x in node.findall(".//HeadingMappedTo/DescriptorReferredTo/DescriptorUI")
                                    for t in descriptor_types.get((x.text or "").lstrip("*"), [])})
                aliases = sorted({x.text for x in node.findall(".//Term/String") if x.text} | {name})
                for entity_type in types:
                    yield {"namespace": "MESH", "id": uid, "name": name, "aliases": aliases,
                           "type": entity_type, "tax_id": None, "source": SOURCES[filename],
                           "source_record_url": "https://meshb.nlm.nih.gov/record/ui?ui=" + uid}
                node.clear()
                root.clear()


def build_kb(documents):
    queries = raw_queries(documents)
    selected, candidates, matched, background = [], Counter(), Counter(), Counter()
    taxonomy = []
    tax_source = "taxonomy_9606_10090_10116.xml"
    for taxon in ET.parse(DATA / "downloads" / tax_source).getroot().findall("Taxon"):
        tax_id = taxon.findtext("TaxId")
        name = taxon.findtext("ScientificName")
        aliases = {name}
        other = taxon.find("OtherNames")
        if other is not None:
            aliases.update(x.text for x in other if x.tag in ("Synonym", "CommonName", "GenbankCommonName", "EquivalentName") and x.text)
        taxonomy.append({"namespace": "NCBITaxon", "id": tax_id, "name": name,
                         "aliases": sorted(aliases), "type": "OrganismTaxon", "tax_id": tax_id,
                         "source": SOURCES[tax_source], "source_record_url": "https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id=" + tax_id})
    for entry in chain(gene_entries(), mesh_entries(), taxonomy):
        candidates[entry["type"]] += 1
        hit = any(normalized(a) in queries and len(normalized(a)) >= 2 for a in entry["aliases"])
        # Fixed independent background sample, not selected with gold IDs.
        digest = hashlib.sha256((entry["namespace"] + ":" + entry["id"]).encode()).hexdigest()
        decoy = int(digest[:8], 16) % 127 == 0
        if hit or decoy or entry["type"] == "OrganismTaxon":
            entry["candidate_selection"] = "raw_text_lexical_match" if hit else "fixed_hash_background"
            selected.append(entry)
            (matched if hit else background)[entry["type"]] += 1
    selected.sort(key=lambda e: (e["namespace"], e["id"], e["type"]))
    return selected, {"source_entries_by_type": dict(candidates), "raw_text_candidates_by_type": dict(matched),
                      "background_candidates_by_type": dict(background), "candidate_count": len(selected),
                      "selection_uses_gold_ids_or_gold_spans": False,
                      "unsupported_types": ["SequenceVariant", "CellLine"],
                      "gene_species": ["9606", "10090", "10116"],
                      "note": "Unsupported IDs remain unresolved; all six entity types remain in the extraction corpus. OMIM-only disease IDs are not remapped to MESH."}


def verify_bundled():
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    for artifact in manifest["artifacts"]:
        path = ROOT / artifact["path"]
        if sha(path) != artifact["sha256"]:
            raise ValueError("Bundled artifact changed: " + artifact["path"])
    print(json.dumps({"passed": True, "artifacts": len(manifest["artifacts"])}))


def publish_staged(stage, paths, old_manifest, *, refresh_lock=False):
    """Validate the entire new snapshot before replacing any bundled file."""
    manifest_path = stage / "data/manifest.json"
    generated = json.loads(manifest_path.read_text(encoding="utf-8"))
    if old_manifest and not refresh_lock:
        expected_sources = {x["file"]: (x["url"], x["sha256"]) for x in old_manifest["sources"]}
        actual_sources = {x["file"]: (x["url"], x["sha256"]) for x in generated["sources"]}
        expected_artifacts = {x["path"]: x["sha256"] for x in old_manifest["artifacts"]}
        actual_artifacts = {x["path"]: x["sha256"] for x in generated["artifacts"]}
        if expected_sources != actual_sources or expected_artifacts != actual_artifacts:
            raise ValueError("Rebuild differs from the locked snapshot; no bundled files were replaced. Review the difference in a separate copy and use --refresh-lock only for an intentional dataset upgrade.")
    # All verification above precedes mutation; manifest is committed last.
    for name in [*paths, "data/manifest.json"]:
        destination = ROOT / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        (stage / name).replace(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="Download missing official snapshots before rebuilding")
    parser.add_argument("--verify-bundled", action="store_true", help="Check frozen bundled JSONL without network")
    parser.add_argument("--size", type=int, default=50)
    parser.add_argument("--refresh-lock", action="store_true", help="Explicitly replace source/artifact locks in a separately reviewed dataset upgrade")
    args = parser.parse_args()
    if args.verify_bundled:
        verify_bundled()
        return
    old_manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8")) if (DATA / "manifest.json").exists() else None
    if old_manifest and not args.refresh_lock:
        verify_bundled()
    if args.fetch or old_manifest:
        # Verify fixed source hashes before deriving any output.
        fetch(refresh_lock=args.refresh_lock)
    records = read_biored()
    selected = select_documents(records, args.size)
    documents = [{k: r[k] for k in ("doc_id", "title", "abstract", "text", "source_split", "split")}
                 | {"source_url": "https://pubmed.ncbi.nlm.nih.gov/" + r["doc_id"] + "/"} for r in selected]
    gold = [{"doc_id": r["doc_id"], "entities": r["entities"], "relations": r["relations"],
             "reference_status": "original_dataset_gold", "source_split": r["source_split"]} for r in selected]
    kb, kb_stats = build_kb(documents)
    with tempfile.TemporaryDirectory(prefix=".prepare-", dir=DATA) as temporary:
        stage = Path(temporary)
        jsonl(stage / "data" / "corpus/documents.jsonl", documents)
        jsonl(stage / "data" / "reference/gold.jsonl", gold)
        jsonl(stage / "data" / "kb/entities.jsonl", kb)
        by_id = defaultdict(list)
        for r in selected:
            for key in sorted(connectivity_ids(r)):
                by_id[key].append(r["doc_id"])
        shared = {k: sorted(v, key=int) for k, v in sorted(by_id.items()) if len(v) > 1}
        dump(stage / "data" / "reference/cross_document_gold.json", shared)
        dump(stage / "data" / "reference/selection_report.json", {
            "algorithm": "deterministic greedy shared gene/disease graph; exclude entities occurring in >45 of 600 documents; one in five selected documents held for incremental import",
            "sampling_uses_gold": True, "prediction_uses_gold": False,
            "limitation": "Purposive connected teaching subset, not an unbiased benchmark sample. Original Train/Dev/Test are retained as provenance; do not report scores as official BioRED test results.",
            "total_documents": len(documents), "initial": sum(d["split"] == "initial" for d in documents),
            "incremental": sum(d["split"] == "incremental" for d in documents),
            "shared_gene_disease_ids": len(shared), "gold_entity_mentions": sum(len(g["entities"]) for g in gold),
            "gold_relations": sum(len(g["relations"]) for g in gold),
            "entity_types": dict(Counter(e["type"] for g in gold for e in g["entities"])),
            "relation_types": dict(Counter(r["type"] for g in gold for r in g["relations"])), "kb": kb_stats,
            "documents": [{"doc_id": d["doc_id"], "title": d["title"], "split": d["split"]} for d in documents]})
        paths = ["data/corpus/documents.jsonl", "data/reference/gold.jsonl", "data/kb/entities.jsonl",
                 "data/reference/cross_document_gold.json", "data/reference/selection_report.json"]
        dump(stage / "data" / "manifest.json", {
            "schema_version": "1.1", "serialization": "UTF-8 JSON sorted keys, fixed array order, newline terminated", "dataset": "BioRED original 600, 2022 release",
            "snapshot_date": "2026-11-12", "text_coordinates": "Python Unicode character offsets; title + newline + abstract; start inclusive, end exclusive; all original spans verified against raw text",
            "sources": [{"file": name, "url": url, "sha256": sha(DATA / "downloads" / name),
                         "bytes": (DATA / "downloads" / name).stat().st_size} for name, url in SOURCES.items()],
            "artifacts": [{"path": p, "sha256": sha(stage / p), "bytes": (stage / p).stat().st_size} for p in paths],
            "kb": kb_stats, "gold_scope": ["entity span", "entity type", "standard entity identifiers", "document-level relation", "novelty"],
            "not_gold": ["sentence rationale", "complete experiment context", "causal direction", "model confidence", "course revision history"]})
        publish_staged(stage, paths, old_manifest, refresh_lock=args.refresh_lock)
    print(json.dumps({"documents": len(documents), "kb": len(kb), "shared_gene_disease_ids": len(shared)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
