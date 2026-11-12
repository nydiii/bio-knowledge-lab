"""Run the complete free workflow and package only its diagnostic summaries."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import zipfile

def main():
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,default=Path("runs/student-check"));args=p.parse_args()
    if args.output.exists(): raise SystemExit("回传目录已存在，请换新路径，避免覆盖。")
    args.output.mkdir(parents=True)
    env={"python":sys.version,"platform":platform.platform(),"machine":platform.machine(),
         "started_at":datetime.now(timezone.utc).isoformat(),"api_calls":0}
    (args.output/"environment.json").write_text(json.dumps(env,ensure_ascii=False,indent=2),encoding="utf-8")
    child_env=os.environ.copy()
    child_env["PYTHONIOENCODING"]="utf-8"
    result=subprocess.run([sys.executable,"-m","bio_knowledge_lab","demo","--workdir",str(args.output/"workflow")],capture_output=True,text=True,encoding="utf-8",env=child_env)
    (args.output/"stdout.log").write_text(result.stdout,encoding="utf-8")
    (args.output/"stderr.log").write_text(result.stderr,encoding="utf-8")
    (args.output/"exit_code.txt").write_text(str(result.returncode),encoding="utf-8")
    target=args.output.with_suffix(".zip")
    with zipfile.ZipFile(target,"w",zipfile.ZIP_DEFLATED) as z:
        for name in ["environment.json","stdout.log","stderr.log","exit_code.txt","workflow/report.json","workflow/run_metadata.json","workflow/evaluation_all.json"]:
            file=args.output/name
            if file.exists(): z.write(file,name)
    print(json.dumps({"passed":result.returncode==0,"return_archive":str(target)},ensure_ascii=False))
    return result.returncode

if __name__=="__main__": raise SystemExit(main())
