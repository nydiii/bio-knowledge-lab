import argparse
import json
import sys
from pathlib import Path
from .io import DATA,ROOT,read_jsonl,write_json,write_jsonl

def parser():
    p=argparse.ArgumentParser(description="生物知识建模实训；免费回放为默认路径")
    sub=p.add_subparsers(dest="command",required=True)
    f=sub.add_parser("fetch",help="下载并核验官方资料与候选词典")
    f.add_argument("--verify-only",action="store_true")
    for command in ("extract","check-evidence"):
        s=sub.add_parser(command)
        s.add_argument("--mode",choices=["replay","api"],default="replay")
        s.add_argument("--split",choices=["initial","incremental","all"],default="all")
        s.add_argument("--input",type=Path)
        s.add_argument("--output",type=Path,required=True)
        s.add_argument("--cache",type=Path)
        s.add_argument("--credentials",type=Path)
        s.add_argument("--ledger",type=Path,default=ROOT/"runs/api-budget.json")
        s.add_argument("--budget-cny",type=float,default=5.0)
    s=sub.add_parser("align")
    s.add_argument("--input",type=Path,required=True);s.add_argument("--output",type=Path,required=True)
    s.add_argument("--method",choices=["lexical","sapbert","contextual"],default="contextual")
    s.add_argument("--kb",type=Path,default=DATA/"kb/entities.jsonl")
    s.add_argument("--mode",choices=["replay","api"],default="replay")
    s.add_argument("--cache",type=Path)
    s.add_argument("--credentials",type=Path)
    s.add_argument("--ledger",type=Path,default=ROOT/"runs/api-budget.json")
    s.add_argument("--budget-cny",type=float,default=5.0)
    for command in ("fuse","update"):
        s=sub.add_parser(command);s.add_argument("--input",type=Path,required=True);s.add_argument("--db",type=Path,required=True)
    s=sub.add_parser("evaluate")
    s.add_argument("--input",type=Path,required=True);s.add_argument("--output",type=Path)
    s.add_argument("--gold",type=Path,default=DATA/"reference/gold.jsonl")
    for command in ("check","query","history"):
        s=sub.add_parser(command);s.add_argument("--db",type=Path,required=True);s.add_argument("--output",type=Path)
    s=sub.add_parser("revise");s.add_argument("--db",type=Path,required=True);s.add_argument("--proposal",type=Path,required=True)
    s=sub.add_parser("prepare-revision");s.add_argument("--db",type=Path,required=True);s.add_argument("--output-dir",type=Path,required=True)
    for command in ("demo","verify"):
        s=sub.add_parser(command);s.add_argument("--workdir",type=Path,default=ROOT/"runs/demo")
    return p

def _client(args):
    if args.mode != "api": return None
    from .api import Client,credentials
    return Client(args.ledger,credentials(args.credentials),args.budget_cny)

def main(argv=None):
    args=parser().parse_args(argv)
    try:
        result=execute(args)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (ValueError,RuntimeError,FileNotFoundError,KeyError) as exc:
        print(f"错误：{exc}",file=sys.stderr)
        return 2

def execute(args):
    from . import pipeline
    command=args.command
    if command=="fetch":
        import subprocess
        cmd=[sys.executable,str(ROOT/"scripts/prepare_data.py")]
        cmd.append("--verify-bundled" if args.verify_only else "--fetch")
        subprocess.run(cmd,check=True)
        return {"completed":True}
    if command=="extract":
        from .extraction import extract_document
        docs=read_jsonl(args.input or DATA/"corpus/documents.jsonl")
        if args.split!="all": docs=[d for d in docs if d["split"]==args.split]
        if args.output.exists(): raise ValueError("输出已存在，请选新路径；API缓存会按提示哈希复用。")
        client=_client(args); records=[]
        cache=args.cache or (DATA/"replay" if args.mode=="replay" else args.output.parent/"api-cache")
        for n,doc in enumerate(docs,1):
            records.append(extract_document(doc,mode=args.mode,cache=cache,client=client))
            print(f"{n}/{len(docs)} {doc['doc_id']}",file=sys.stderr,flush=True)
        write_jsonl(args.output,records)
        return {"documents":len(records),"mode":args.mode,"output":str(args.output)}
    if command=="check-evidence":
        from .verification import check_record
        if args.input is None: raise ValueError("check-evidence 需要 --input 对齐后的记录文件")
        records=read_jsonl(args.input)
        if args.split!="all": records=[d for d in records if d["split"]==args.split]
        if args.output.exists(): raise ValueError("输出已存在，请选新路径")
        docs=read_jsonl(DATA/"corpus/documents.jsonl");client=_client(args)
        cache=args.cache or (DATA/"replay" if args.mode=="replay" else args.output.parent/"api-cache")
        results=[]
        for n,record in enumerate(records,1):
            results.append(check_record(record,docs,mode=args.mode,cache=cache,client=client))
            print(f"核查 {n}/{len(records)} {record['doc_id']}",file=sys.stderr,flush=True)
        write_jsonl(args.output,results)
        return {"documents":len(results),"status":"model_candidates_not_gold","output":str(args.output)}
    if command=="align":
        if args.method=="contextual":
            from .contextual_alignment import align_contextual
            cache=args.cache or (DATA/"replay" if args.mode=="replay" else args.output.parent/"api-cache")
            records=align_contextual(read_jsonl(args.input),args.kb,mode=args.mode,cache=cache,client=_client(args))
        else:
            records=pipeline.align_records(read_jsonl(args.input),args.kb,method=args.method)
        write_jsonl(args.output,records)
        return {"documents":len(records),"method":args.method,"output":str(args.output)}
    if command in ("fuse","update"):
        return pipeline.ingest_records(args.db,read_jsonl(args.input))
    if command=="evaluate":
        result=pipeline.evaluate_records(read_jsonl(args.input),args.gold)
    elif command=="check": result=pipeline.validate_database(args.db)
    elif command=="query": result=pipeline.query_database(args.db)
    elif command=="history": result=pipeline.history(args.db)
    elif command=="revise":
        return pipeline.apply_revision(args.db,json.loads(args.proposal.read_text(encoding="utf-8")))
    elif command=="prepare-revision":
        from .demo import prepare_revision
        return prepare_revision(args.db,args.output_dir)
    elif command in ("demo","verify"):
        from .demo import run_demo,verify_demo
        return run_demo(args.workdir) if command=="demo" else verify_demo(args.workdir)
    else: raise ValueError("unknown command")
    if getattr(args,"output",None): write_json(args.output,result)
    return result
