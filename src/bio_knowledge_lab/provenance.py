import hashlib
import json
from .io import ROOT,DATA

def verify_artifacts():
    count=0
    for name in ("manifest.json","replay_manifest.json"):
        path=DATA/name
        manifest=json.loads(path.read_text(encoding="utf-8"))
        for entry in manifest["artifacts"]:
            file=ROOT/entry["path"]
            if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest()!=entry["sha256"]:
                raise ValueError("冻结资料哈希不匹配: "+entry["path"])
            count+=1
    return {"passed":True,"verified_artifacts":count}
