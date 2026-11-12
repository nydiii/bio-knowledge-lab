"""Maintainer-only real replay generation; every request uses ONE shared ledger.

No key literals, gold labels, or synthetic fallback. Interrupted runs reuse valid
responses; failed unknown outcomes require inspection instead of automatic retry.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
from pathlib import Path
from bio_knowledge_lab.api import Client,credentials
from bio_knowledge_lab.io import DATA,ROOT,read_jsonl,write_json,write_jsonl
from bio_knowledge_lab.extraction import extract_document

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--credentials",type=Path,required=True)
    p.add_argument("--stage",choices=["extract","link","check"],default="extract")
    p.add_argument("--workers",type=int,default=3)
    args=p.parse_args()
    client=Client(ROOT/"runs/api-budget.json",credentials(args.credentials),5.0)
    docs=read_jsonl(DATA/"corpus/documents.jsonl")
    if args.stage=="extract":
        jobs=docs
        def run(doc): return extract_document(doc,mode="api",cache=DATA/"replay",client=client)
        output=ROOT/"runs/generated_extractions.jsonl"
    elif args.stage=="link":
        from bio_knowledge_lab.contextual_alignment import align_contextual
        jobs=read_jsonl(ROOT/"runs/generated_extractions.jsonl")
        def run(doc): return align_contextual([doc],DATA/"kb/entities.jsonl",mode="api",cache=DATA/"replay",client=client)[0]
        output=ROOT/"runs/aligned_contextual.jsonl"
    else:
        from bio_knowledge_lab.verification import check_record
        jobs=read_jsonl(ROOT/"runs/aligned_all.jsonl")
        def run(doc): return check_record(doc,docs,mode="api",cache=DATA/"replay",client=client)
        output=ROOT/"runs/generated_checks.jsonl"
    results=[];errors=[]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        tasks={pool.submit(run,doc):doc["doc_id"] for doc in jobs}
        for task in as_completed(tasks):
            did=tasks[task]
            try:
                results.append(task.result())
                print(json.dumps({"completed":len(results),"total":len(jobs),"doc_id":did}),flush=True)
            except Exception as exc:
                errors.append({"doc_id":did,"error_type":type(exc).__name__,"message":str(exc)})
                print(json.dumps(errors[-1],ensure_ascii=False),flush=True)
    order={d["doc_id"]:i for i,d in enumerate(docs)}
    results.sort(key=lambda d:order[d["doc_id"]])
    write_jsonl(output,results)
    write_json(output.with_suffix(".status.json"),{"successful":len(results),"total":len(jobs),"errors":errors})
    if errors: raise SystemExit(2)

if __name__=="__main__": main()
