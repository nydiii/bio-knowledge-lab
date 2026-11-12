"""Build publication artifacts from completed real runs; makes no API requests."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import platform
from bio_knowledge_lab import pipeline
from bio_knowledge_lab.io import ROOT,DATA,read_jsonl,write_json

def main():
    reports=ROOT/"reports";reports.mkdir(exist_ok=True)
    metrics={}
    for name,file in [("lexical","aligned_lexical_final.jsonl"),("sapbert","aligned_sapbert_final.jsonl"),("contextual","aligned_contextual.jsonl")]:
        metrics[name]=pipeline.evaluate_records(read_jsonl(ROOT/"runs"/file),DATA/"reference/gold.jsonl")
    write_json(reports/"metrics.json",metrics)
    records=read_jsonl(ROOT/"runs/aligned_contextual.jsonl")
    checks=read_jsonl(ROOT/"runs/generated_checks.jsonl")
    check_counts=Counter(j["label"] for c in checks for j in c["judgments"])
    ledger=json.loads((ROOT/"runs/api-budget.json").read_text(encoding="utf-8"))
    budget={"ceiling_cny":ledger["ceiling_cny"],"pricing":ledger["pricing"],"api_calls":len(ledger["calls"]),
        "cost_upper_cny_peak_no_cache":round(sum(c.get("charged_upper_cny",c["reserved_cny"]) for c in ledger["calls"]),6),
        "input_tokens":sum(c.get("usage",{}).get("prompt_tokens",0) for c in ledger["calls"]),
        "output_tokens":sum(c.get("usage",{}).get("completion_tokens",0) for c in ledger["calls"]),
        "status_counts":dict(Counter(c["status"] for c in ledger["calls"])),
        "billing_statement_verified":False,
        "note":"Includes earlier authentic alignment experiment and corrected reruns; these are conservative estimates, not account invoices.",
        "calls":[{k:v for k,v in c.items() if k!="response_path"} for c in ledger["calls"]]}
    write_json(reports/"api_usage.json",budget)
    manifest={"schema_version":"1.0","artifacts":[]}
    for file in sorted((DATA/"replay").glob("*.json")):
        manifest["artifacts"].append({"path":str(file.relative_to(ROOT)),"sha256":hashlib.sha256(file.read_bytes()).hexdigest()})
    write_json(DATA/"replay_manifest.json",manifest)
    gold={d["doc_id"]:d for d in read_jsonl(DATA/"reference/gold.jsonl")}
    rows=[]
    for record in records:
        refs={(e["start"],e["end"],e["type"]):e for e in gold[record["doc_id"]]["entities"]}
        for entity in record["entities"]:
            ref=refs.get((entity["start"],entity["end"],entity["type"]))
            actual={(l["namespace"],str(l["id"])) for l in entity.get("links",[])}
            expected={(l["namespace"],str(l["id"])) for l in ref.get("ids",[])} if ref else set()
            if actual and expected and actual!=expected:
                rows.append({"doc_id":record["doc_id"],"record_id":entity["mention_id"],"issue":"id_differs_from_dataset_reference",
                    "text":entity["text"],"prediction":json.dumps(sorted(actual)),"reference":json.dumps(sorted(expected)),
                    "source_url":record["source_url"],"source_context":record["text"][max(0,entity["start"]-160):entity["end"]+200],
                    "review_note":"核对物种、对象粒度及数据库版本；不要静默改原金标。","decision":"","reviewer":""})
    for c in checks:
        record=next(r for r in records if r["doc_id"]==c["doc_id"])
        for j in c["judgments"]:
            if j["label"] in ("contradicted_text","invalid_judgment","missing_judgment","insufficient_text"):
                rows.insert(0,{"doc_id":c["doc_id"],"record_id":j["relation_id"],"issue":j["label"],
                    "text":j.get("reason",""),"prediction":json.dumps(next(r for r in record["relations"] if r["relation_id"]==j["relation_id"]),ensure_ascii=False),
                    "reference":"No sentence-level gold","source_url":record["source_url"],"source_context":record["text"],
                    "review_note":"模型核查是候选，不是独立人工判断。","decision":"","reviewer":""})
    priority={"contradicted_text":0,"invalid_judgment":1,"missing_judgment":2,
              "id_differs_from_dataset_reference":3,"insufficient_text":4}
    rows.sort(key=lambda row:(priority[row["issue"]],row["doc_id"],row["record_id"]))
    fields=["doc_id","record_id","issue","text","prediction","reference","source_url","source_context","review_note","decision","reviewer"]
    for name,items in [("review_queue.csv",rows),("priority_review.csv",rows[:24])]:
        with (reports/name).open("w",encoding="utf-8-sig",newline="") as f:
            writer=csv.DictWriter(f,fields,lineterminator="\n");writer.writeheader();writer.writerows(items)
    write_json(reports/"run_summary.json",{"documents":len(records),"entity_mentions":sum(len(r["entities"]) for r in records),
        "candidate_relations":sum(len(r["relations"]) for r in records),"verification_labels":dict(check_counts),
        "review_queue_rows":len(rows),"priority_review_rows":min(len(rows),24),"platform":platform.platform(),
        "python":platform.python_version(),"scientific_review_complete":False,"model_evidence_labels_are_not_accuracy":True})
    print(json.dumps({"reports":str(reports),"cost_upper_cny":budget["cost_upper_cny_peak_no_cache"],"calls":budget["api_calls"],"review_rows":len(rows)},ensure_ascii=False))

if __name__=="__main__": main()
