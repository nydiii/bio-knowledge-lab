"""A four-step, offline improvement experience; references never predict IDs."""
from collections import Counter
import hashlib
import json
from pathlib import Path

from .io import DATA, ROOT, read_jsonl, write_json, write_jsonl
from .pipeline import evaluate_records, _type


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _text(path, lines):
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _ids(entity, field="links"):
    return tuple(sorted((str(x["namespace"]), str(x["id"])) for x in entity.get(field, [])))


def _show(ids):
    return "; ".join(f"{ns}:{identifier}" for ns, identifier in ids) or "未确定"


def _position(entity):
    return entity["start"], entity["end"], _type(entity["type"])


def _validate_comparable(old, new):
    if len(old) != len(new):
        raise ValueError("本轮不应增加或删除文献")
    for before, after in zip(old, new):
        if before["doc_id"] != after["doc_id"] or before["text"] != after["text"]:
            raise ValueError("本轮不应改变文献身份、顺序或原文")
        if len(before["entities"]) != len(after["entities"]) or len(before["relations"]) != len(after["relations"]):
            raise ValueError("本轮不应增加或删除实体提及及关系记录")
        for a, b in zip(before["entities"], after["entities"]):
            if any(a[k] != b[k] for k in ("mention_id", "start", "end", "type", "text")):
                raise ValueError("本轮不应改变实体抽取")
        for a, b in zip(before["relations"], after["relations"]):
            if any(a.get(k) != b.get(k) for k in ("relation_id", "head", "tail", "novelty")):
                raise ValueError("本轮不应更换关系身份、端点或 novelty")


def _references():
    return {d["doc_id"]: d for d in read_jsonl(DATA / "reference/gold.jsonl")}


def _gold_entity(ref, entity):
    return next((e for e in ref["entities"] if _position(e) == _position(entity)), {})


def _relation_reference(record, relation, ref):
    entities = {e["mention_id"]: e for e in record["entities"]}
    left = set(_ids(_gold_entity(ref, entities[relation["head"]]), "ids"))
    right = set(_ids(_gold_entity(ref, entities[relation["tail"]]), "ids"))
    labels = set()
    for r in ref["relations"]:
        h, t = set(_ids(r, "head_ids")), set(_ids(r, "tail_ids"))
        if (left & h and right & t) or (left & t and right & h):
            labels.add(r["type"])
    return "; ".join(sorted(labels)) or "无法按本次提及跨度直接匹配参考端点"


def _cases():
    return json.loads((DATA / "improvement/review_cases.json").read_text(encoding="utf-8"))


def _metric_lines(old, new=None):
    lines = ["| 指标 | 旧版 precision / recall / F1 | 新版 precision / recall / F1 |", "|---|---|---|"]
    for key, title in [("ner_strict", "实体识别"), ("linking_strict", "严格链接"),
                       ("relation_end_to_end", "端到端关系"), ("relation_with_novelty", "关系及 novelty")]:
        def display(metric):
            return " / ".join(f"{100 * metric[k]:.2f}%" for k in ("precision", "recall", "f1"))
        lines.append(f"| {title} | {display(old[key])} | {display(new[key]) if new else '尚未运行'} |")
    return lines


def _check_baseline(folder):
    if not (folder / "run.json").exists():
        raise ValueError("请先运行 --step baseline，并在后续步骤使用同一个 --workdir。")
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    for filename, expected in run["baseline_hashes"].items():
        if _hash(folder / filename) != expected:
            raise ValueError("旧版文件已被修改，请保留原结果，在新目录重新运行 baseline：" + filename)
    for filename, expected in run["resource_hashes"].items():
        if _hash(ROOT / filename) != expected:
            raise ValueError("实验资源版本已改变，请使用新目录重新运行 baseline：" + filename)
    return run


def _verify_resources():
    for path in [DATA / "manifest.json", DATA / "replay_manifest.json", DATA / "improvement/manifest.json"]:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        for artifact in manifest["artifacts"]:
            if _hash(ROOT / artifact["path"]) != artifact["sha256"]:
                raise ValueError("课程资源哈希不匹配：" + artifact["path"])


def baseline(folder):
    from .extraction import extract_document
    from .contextual_alignment import align_contextual
    folder.mkdir(parents=True, exist_ok=True)
    if any(folder.iterdir()):
        raise ValueError("体验目录已有文件。为保留旧结果，请换一个新的 --workdir。")
    _verify_resources()
    docs = read_jsonl(DATA / "corpus/documents.jsonl")
    extracted = [extract_document(d, mode="replay") for d in docs]
    records = align_contextual(extracted, DATA / "kb/entities.jsonl", mode="replay")
    write_jsonl(folder / "baseline.jsonl", records)
    metrics = evaluate_records(records, DATA / "reference/gold.jsonl")
    write_json(folder / "baseline_evaluation.json", metrics)
    resources = [DATA / "reference/gold.jsonl", DATA / "improvement/entities.jsonl",
                 DATA / "improvement/cell_context.json", DATA / "improvement/review_cases.json"]
    write_json(folder / "run.json", {
        "mode": "authentic_replay_then_local_rules", "new_api_calls": 0,
        "baseline_hashes": {name: _hash(folder / name) for name in ["baseline.jsonl", "baseline_evaluation.json"]},
        "resource_hashes": {str(p.relative_to(ROOT)): _hash(p) for p in resources},
        "development_doc_ids": _cases()["development_doc_ids"],
        "validation_scope": "未参与本轮规则修改的其余文献；历史开发已可见，不是独立测试集。",
    })
    return {"step": "baseline", "documents": len(records), "api_calls": 0,
            "message": "旧版真实回放已保存。下一步 inspect 查看具体问题。", "evaluation": str(folder / "baseline_evaluation.json")}


def inspect(folder):
    _check_baseline(folder)
    records = {d["doc_id"]: d for d in read_jsonl(folder / "baseline.jsonl")}
    references, cases = _references(), _cases()
    lines = ["# 从旧结果发现问题", "", "本页自动生成，只需按教程阅读，不用填写或提交。",
             "", "24 份审阅意见覆盖 22/24 条不同记录；第 11、12 条未审。意见按字段保留，参考辅助整理不冒充独立专家金标。",
             "", "先看 15、23 条的名称与 ID，再看 1、4、6 条的关系语义；8 条展示引文问题，13、14 条展示原参考争议。"]
    for case in cases["cases"]:
        record = records[case["doc_id"]]
        ref = references[case["doc_id"]]
        entity = next((e for e in record["entities"] if e["mention_id"] == case["record_id"]), None)
        lines += ["", f"## 第 {case['number']} 条 · {case['doc_id']}/{case['record_id']}", "",
                  f"核查字段：`{case['reviewed_field']}`；当前归类：`{case['review_status']}`。"]
        if entity:
            context = record["text"][max(0, entity["start"] - 180):entity["end"] + 240]
            methods = ", ".join(sorted({x.get("method", "unknown") for x in entity.get("links", [])}))
            lines += ["", f"原文名称：**{entity['text']}**，位置 `[{entity['start']}, {entity['end']})`。",
                      "", f"旧版：`{_show(_ids(entity))}`；产生方式：`{methods or entity.get('link_status')}`。",
                      "", f"原 BioRED 参考：`{_show(_ids(_gold_entity(ref, entity), 'ids'))}`。"]
        else:
            relation = next(r for r in record["relations"] if r["relation_id"] == case["record_id"])
            by_id = {e["mention_id"]: e for e in record["entities"]}
            left, right = by_id[relation["head"]], by_id[relation["tail"]]
            context = record["text"]
            lines += ["", f"关系对象：**{left['text']} — {right['text']}**。",
                      "", f"旧标签：`{relation['type']}`；固定参考：`{_relation_reference(record, relation, ref)}`。",
                      "", f"旧端点 ID：`{_show(_ids(left))}` — `{_show(_ids(right))}`。标签合理不代表端点已经正确。"]
        lines += ["", f"本次核查：{case['review_summary']}", "", "来源片段：", "",
                  *["> " + part for part in context.splitlines()], "", f"[查看原文]({case['source_url']})"]
    _text(folder / "inspection.md", lines)
    return {"step": "inspect", "message": "诊断说明已生成；只需阅读，无需交表。", "open": str(folder / "inspection.md")}


def optimize(folder):
    _check_baseline(folder)
    if (folder / "improved.jsonl").exists():
        raise ValueError("新版结果已经存在。请先 compare；若重新实验，请换新 --workdir 从 baseline 开始。")
    from .improvement import improve_records
    from .relation_rules import improve_relation_evidence
    records = read_jsonl(folder / "baseline.jsonl")
    improved = improve_records(records, DATA / "improvement/entities.jsonl", DATA / "improvement/cell_context.json")
    improved = improve_relation_evidence(improved)
    _validate_comparable(records, improved)
    for old, new in zip(records, improved):
        new["improvement"]["relation_labels_changed"] = any(a["type"] != b["type"] for a, b in zip(old["relations"], new["relations"]))
    write_jsonl(folder / "improved.jsonl", improved)
    # Evaluation is downstream of prediction. These labels never enter a rule.
    write_json(folder / "improved_evaluation.json", evaluate_records(improved, DATA / "reference/gold.jsonl"))
    write_json(folder / "improved_run.json", {"output_sha256": _hash(folder / "improved.jsonl"),
                "api_calls": 0, "method": "local_rules_on_fixed_authentic_predictions", "human_confirmed": False,
                "code_hashes": {name: _hash(Path(__file__).with_name(name)) for name in ("improvement.py", "relation_rules.py")}})
    return {"step": "optimize", "message": "本地规则改进已运行，原始抽取和旧结果保留。下一步 compare 查看改善与退步。",
            "api_calls": 0, "output": str(folder / "improved.jsonl")}


def compare(folder):
    run = _check_baseline(folder)
    if not (folder / "improved_run.json").exists():
        raise ValueError("请先运行 --step optimize。")
    improved_run = json.loads((folder / "improved_run.json").read_text(encoding="utf-8"))
    if _hash(folder / "improved.jsonl") != improved_run["output_sha256"]:
        raise ValueError("新版预测文件被修改，不能将手改结果当作算法结果。")
    old, new = read_jsonl(folder / "baseline.jsonl"), read_jsonl(folder / "improved.jsonl")
    _validate_comparable(old, new)
    refs = _references()
    development = set(run["development_doc_ids"])
    groups = [("开发案例", development), ("本轮未参与调整的验证文献", {r["doc_id"] for r in old} - development),
              ("全部文献", {r["doc_id"] for r in old})]
    lines = ["# 旧版与改进版：实际运行比较", "", "本页由实际输出计算，只需阅读，不用填写或提交。",
             "", "新版是固定模型回答上的本地规则改进，本次没有新模型推理。原抽取跨度/类型不变，实体识别分数应不变。",
             "", "两版使用相同的原 BioRED 金标和评价器。下面是与固定参考的一致性，不是专家审定率；原参考争议也照常计分。"]
    metrics = {}
    for title, ids in groups:
        before = evaluate_records([r for r in old if r["doc_id"] in ids], DATA / "reference/gold.jsonl")
        after = evaluate_records([r for r in new if r["doc_id"] in ids], DATA / "reference/gold.jsonl")
        metrics[title] = {"before": before, "after": after}
        lines += ["", f"## {title}（{len(ids)} 篇）", "", *_metric_lines(before, after)]
    lines += ["", "开发案例的改善只能证明这些案例被修复。本轮验证文献历史开发已可见，不是全新的独立测试集。",
              "", "## 所有实体链接的变化", "", "严格判定要求位置、类型和完整 ID 集合一致；撤回错误候选为待审不等于已经找到正确 ID。"]
    changes, counts = [], Counter()
    for before, after in zip(old, new):
        for e, n in zip(before["entities"], after["entities"]):
            expected = _ids(_gold_entity(refs[before["doc_id"]], e), "ids")
            a, b = _ids(e), _ids(n)
            if expected:
                result = "改善" if a != expected and b == expected else "退步" if a == expected and b != expected else "未变（匹配）" if b == expected else "仍未匹配"
            else:
                result = "无可匹配的参考提及"
            counts[result] += 1
            if a != b:
                changes.append({"doc_id": before["doc_id"], "mention_id": e["mention_id"], "text": e["text"],
                                "before": a, "after": b, "reference": expected, "result": result,
                                "reason": n.get("improvement_review", {}).get("reason", "")})
    lines += ["", "；".join(f"{k}：{counts[k]}" for k in ("改善", "退步", "未变（匹配）", "仍未匹配", "无可匹配的参考提及")) + "。",
              "", f"发生 ID 集合变化的提及：{len(changes)}。", "",
              "| 文献/提及 | 名称 | 旧 ID | 新 ID | 原参考 | 结果 |", "|---|---|---|---|---|---|"]
    for c in changes:
        lines.append(f"| {c['doc_id']}/{c['mention_id']} | {c['text'].replace('|', '/')} | {_show(c['before'])} | {_show(c['after'])} | {_show(c['reference'])} | {c['result']} |")
    review_counts = Counter(e["improvement_review"]["status"] for d in new for e in d["entities"] if "improvement_review" in e)
    lines += ["", f"另有 {review_counts['needs_review']} 个提及附加待核查提示。这是规则发现的风险，不是已证实错误；旧候选 ID 可能仍保留，不能计为已经修复。"]
    lines += ["", "## 关系标签变化", "", "仅列实际改动；来源句支持是规则候选，不代表所有端点身份也已正确。"]
    relation_changes = []
    for before, after in zip(old, new):
        for r, n in zip(before["relations"], after["relations"]):
            if r["type"] != n["type"]:
                item = {"doc_id": before["doc_id"], "relation_id": r["relation_id"], "before": r["type"], "after": n["type"],
                        "reference": _relation_reference(before, r, refs[before["doc_id"]])}
                relation_changes.append(item)
                lines += ["", f"- `{item['doc_id']}/{item['relation_id']}`：{item['before']} → {item['after']}；固定参考：{item['reference']}。"]
    lines += ["", "## 本轮优先核查的记录现在怎样了", "",
              "下面逐条显示实际预测；原参考辅助整理或人工建议不是算法必然能输出的答案。"]
    by_old, by_new = ({d["doc_id"]: d for d in values} for values in (old, new))
    for case in _cases()["cases"]:
        before, after = by_old[case["doc_id"]], by_new[case["doc_id"]]
        a = next((e for e in before["entities"] if e["mention_id"] == case["record_id"]), None)
        if a:
            b = next(e for e in after["entities"] if e["mention_id"] == case["record_id"])
            value = f"{_show(_ids(a))} → {_show(_ids(b))}"
            trace = b.get("improvement_review", {})
            note = f"{trace.get('status', 'not_rechecked')}；{trace.get('reason', '')}"
        else:
            a = next(r for r in before["relations"] if r["relation_id"] == case["record_id"])
            b = next(r for r in after["relations"] if r["relation_id"] == case["record_id"])
            value = f"{a['type']} → {b['type']}"
            note = b.get("relation_rule_review", {}).get("status", "本轮未自动修改；继续参照诊断说明核查具体字段")
        lines += ["", f"- 第 {case['number']} 条 `{case['doc_id']}/{case['record_id']}`：{value}。{note.rstrip('。')}。"]
    lines += ["", "## 怎样理解仍然存在的问题", "",
              "- insulin 的细胞物种不等于外加试剂物种；多 ID 原参考也不能用全部候选机械填满。保留待审是透明处理，未计作严格修复。",
              "- VIP、DAPT 与 Hsp90beta 的干预方向/对象粒度仍需按原文解释，不能由一个动词自动改标签。",
              "- p19、TRFP 的原参考疑点单独记录；不修改原 gold 追求更高分。",
              "- invalid_judgment 是原核查引文/输出未通过，不能直接说关系错了。本轮未重新调用核查模型，也未把旧核查结果冒充新版判决。",
              "- 原文、候选、金标和规则候选来源仍各自保留；软件通过、分数提高、科学审定和论文严格复现是不同结论。"]
    write_json(folder / "comparison.json", {"groups": metrics, "entity_outcomes": dict(counts), "entity_changes": changes,
              "link_review_status_counts": dict(review_counts),
              "relation_changes": relation_changes, "new_api_calls": 0, "scientific_review_complete": False})
    _text(folder / "comparison.md", lines)
    return {"step": "compare", "message": "比较已完成。打开说明依次查看总体分数、改善与退步及仍待审问题，无需提交表格。",
            "open": str(folder / "comparison.md"), "entity_changes": len(changes), "relation_changes": len(relation_changes)}


def run_feedback_lab(step, workdir):
    return {"baseline": baseline, "inspect": inspect, "optimize": optimize, "compare": compare}[step](Path(workdir))
