"""A complete offline replay, controlled corruption, revision, and increment."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
from . import pipeline
from .extraction import extract_document
from .io import DATA,read_jsonl,write_json,write_jsonl,digest
from .verification import check_record
from .contextual_alignment import align_contextual

def prepare_revision(db_path,output_dir):
    """Teacher operation ONLY: consult fixed gold to design a known-error lesson.

    Extraction/alignment never call this function. Original model records remain
    unchanged in their raw cache and exported extraction files.
    """
    output_dir=Path(output_dir)
    records=pipeline.current_records(db_path)
    references={r["doc_id"]:r for r in read_jsonl(DATA/"reference/gold.jsonl")}
    query=pipeline.query_database(db_path)
    for record in records:
        gold=references.get(record["doc_id"])
        if not gold: continue
        reference_keys=pipeline._relation_keys(gold,gold=True)
        # Select a single unique concept relation so the corruption has an
        # observable effect under document-level relation scoring.
        counts=Counter()
        keys_by_id={}
        for rel in record["relations"]:
            keys=pipeline._relation_keys({**record,"relations":[rel]})
            keys_by_id[rel["relation_id"]]=keys
            counts.update(keys)
        for rel in record["relations"]:
            keys=keys_by_id[rel["relation_id"]]
            if len(keys)!=1 or not keys<=reference_keys or any(counts[k]!=1 for k in keys): continue
            wrong="Negative_Correlation" if rel["type"]!="Negative_Correlation" else "Positive_Correlation"
            faulty=deepcopy(record)
            target=next(r for r in faulty["relations"] if r["relation_id"]==rel["relation_id"])
            target.update(type=wrong,teaching_error=True)
            bad_keys=pipeline._relation_keys({**faulty,"relations":[target]})
            if bad_keys & reference_keys: continue
            version=query["versions"][record["doc_id"]]
            injection={"doc_id":record["doc_id"],"expected_version":version,"replacement":faulty,
                "kind":"teaching_injection","actor":"course_script",
                "reason":"明确注入的教学错误：改变一条与原数据集参考标注一致的关系类别；不是模型实际错误。",
                "evidence":[]}
            correction={"doc_id":record["doc_id"],"expected_version":version+1,"replacement":record,
                "kind":"correction","actor":"course_reference_restore",
                "reason":"恢复教学注入前的关系类别；依据 BioRED 文档级原始人工标注，未声称新增专家审校。",
                "evidence":[{"start":0,"end":len(record["text"]),"text":record["text"]}]}
            info={"doc_id":record["doc_id"],"relation_id":rel["relation_id"],"correct_type":rel["type"],
                  "injected_type":wrong,"source_url":record.get("source_url"),
                  "gold_sha256":digest((DATA/"reference/gold.jsonl").read_text(encoding="utf-8")),
                  "reference_kind":"original_dataset_document_level_gold",
                  "new_human_review":False}
            write_json(output_dir/"teaching_injection.json",injection)
            write_json(output_dir/"correction.json",correction)
            write_json(output_dir/"revision_lesson.json",info)
            return info
    raise ValueError("当前记录没有找到可与原金标对应的独立关系；不能编造修订参考答案。")

def run_demo(workdir):
    workdir=Path(workdir)
    if workdir.exists() and any(workdir.iterdir()):
        raise ValueError("实验目录不是空目录；复核请用verify，重做请换新目录。")
    workdir.mkdir(parents=True,exist_ok=True)
    docs=read_jsonl(DATA/"corpus/documents.jsonl")
    initial=[d for d in docs if d["split"]=="initial"]
    incremental=[d for d in docs if d["split"]=="incremental"]
    db=workdir/"knowledge.sqlite"
    records=[extract_document(d) for d in initial]
    write_jsonl(workdir/"extracted_initial.jsonl",records)
    aligned=align_contextual(records,DATA/"kb/entities.jsonl")
    write_jsonl(workdir/"aligned_initial.jsonl",aligned)
    pipeline.ingest_records(db,aligned)
    query_initial=pipeline.query_database(db)
    write_json(workdir/"query_initial.json",query_initial)
    initial_eval=pipeline.evaluate_records(aligned,DATA/"reference/gold.jsonl")
    write_json(workdir/"evaluation_initial.json",initial_eval)
    checks=[check_record(r,docs) for r in aligned]
    write_jsonl(workdir/"verification_candidates.jsonl",checks)
    lesson=prepare_revision(db,workdir)
    pipeline.apply_revision(db,json.loads((workdir/"teaching_injection.json").read_text(encoding="utf-8")))
    write_json(workdir/"query_injected.json",pipeline.query_database(db))
    injected_eval=pipeline.evaluate_records(pipeline.current_records(db),DATA/"reference/gold.jsonl")
    write_json(workdir/"evaluation_injected.json",injected_eval)
    pipeline.apply_revision(db,json.loads((workdir/"correction.json").read_text(encoding="utf-8")))
    write_json(workdir/"query_corrected.json",pipeline.query_database(db))
    corrected_eval=pipeline.evaluate_records(pipeline.current_records(db),DATA/"reference/gold.jsonl")
    write_json(workdir/"evaluation_corrected.json",corrected_eval)
    new_records=[extract_document(d) for d in incremental]
    write_jsonl(workdir/"extracted_incremental.jsonl",new_records)
    new_aligned=align_contextual(new_records,DATA/"kb/entities.jsonl")
    write_jsonl(workdir/"aligned_incremental.jsonl",new_aligned)
    checks.extend(check_record(r,docs) for r in new_aligned)
    write_jsonl(workdir/"verification_candidates.jsonl",checks)
    pipeline.ingest_records(db,new_aligned)
    history_before_repeat=digest(pipeline._json(pipeline.history(db)))
    repeat=pipeline.ingest_records(db,new_aligned)
    history_after_repeat=digest(pipeline._json(pipeline.history(db)))
    write_json(workdir/"query_updated.json",pipeline.query_database(db))
    write_json(workdir/"validation.json",pipeline.validate_database(db))
    write_json(workdir/"history.json",pipeline.history(db))
    write_json(workdir/"evaluation_all.json",pipeline.evaluate_records(pipeline.current_records(db),DATA/"reference/gold.jsonl"))
    write_json(workdir/"run_metadata.json",{"mode":"authentic_replay","api_calls":0,"cost_cny":0,
        "initial_documents":len(initial),"incremental_documents":len(incremental),"repeat_import":repeat,
        "history_hash_before_repeat":history_before_repeat,"history_hash_after_repeat":history_after_repeat,
        "revision_lesson":lesson,"scientific_review_complete":False})
    report=verify_demo(workdir)
    write_json(workdir/"report.json",report)
    return report

def verify_demo(workdir):
    from .provenance import verify_artifacts
    integrity=verify_artifacts()
    workdir=Path(workdir)
    db=workdir/"knowledge.sqlite"
    docs=read_jsonl(DATA/"corpus/documents.jsonl")
    q=pipeline.query_database(db)
    validation=pipeline.validate_database(db)
    initial=json.loads((workdir/"query_initial.json").read_text(encoding="utf-8"))
    injected=json.loads((workdir/"query_injected.json").read_text(encoding="utf-8"))
    corrected=json.loads((workdir/"query_corrected.json").read_text(encoding="utf-8"))
    lesson=json.loads((workdir/"revision_lesson.json").read_text(encoding="utf-8"))
    metadata=json.loads((workdir/"run_metadata.json").read_text(encoding="utf-8"))
    checks=read_jsonl(workdir/"verification_candidates.jsonl")
    history=pipeline.history(db)
    versions=[x for x in history if x["doc_id"]==lesson["doc_id"]]
    expected_initial=sum(d["split"]=="initial" for d in docs)
    reference_texts={d["doc_id"]:d["text"] for d in docs}
    current=pipeline.current_records(db)
    def target_type(query):
        return next((r["type"] for r in query["relations"] if r["doc_id"]==lesson["doc_id"] and r["relation_id"]==lesson["relation_id"]),None)
    def snapshot_type(snapshot):
        return next((r["type"] for r in snapshot["record"]["relations"] if r["relation_id"]==lesson["relation_id"]),None)
    expected_review=Counter((r["doc_id"],rel["relation_id"]) for r in current for rel in r["relations"])
    actual_review=Counter((r["doc_id"],j["relation_id"]) for r in checks for j in r["judgments"])
    reviews_by_doc={r["doc_id"]:r for r in checks}
    review_coverage=(Counter(r["doc_id"] for r in checks)==Counter(reference_texts.keys())
                     and actual_review==expected_review)
    # Rebuild from the immutable response cache, not from gold or a new API call.
    # Invalid/missing model judgments remain explicit pending rows, not false passes
    # of scientific correctness. This check only verifies authentic review coverage.
    review_replay_match=review_coverage and all(reviews_by_doc[r["doc_id"]]==check_record(r,docs) for r in current)
    history_by_doc={doc_id:[v for v in history if v["doc_id"]==doc_id] for doc_id in reference_texts}
    history_versions=(set(v["doc_id"] for v in history)==set(reference_texts) and all(
        [v["version"] for v in items]==([1,2,3] if doc_id==lesson["doc_id"] else [1])
        and q["versions"].get(doc_id)==items[-1]["version"]
        for doc_id,items in history_by_doc.items()))
    history_hashes=all(v["record_hash"]==digest(pipeline._json(v["record"]))
        and v["record"]["doc_id"]==v["doc_id"] and v["record"]["text"]==reference_texts.get(v["doc_id"])
        for v in history)
    history_transition=False
    if len(versions)==3:
        faulty=deepcopy(versions[0]["record"])
        target=next((r for r in faulty["relations"] if r["relation_id"]==lesson["relation_id"]),None)
        if target is not None:
            target.update(type=lesson["injected_type"],teaching_error=True)
            history_transition=(snapshot_type(versions[0])==lesson["correct_type"]
                and versions[1]["record"]==faulty and versions[2]["record"]==versions[0]["record"])
    incremental_ids={d["doc_id"] for d in docs if d["split"]=="incremental"}
    repeat=metadata.get("repeat_import",{})
    repeat_unchanged=(repeat.get("added")==0 and repeat.get("unchanged")==len(incremental_ids)
        and repeat.get("added_doc_ids")==[] and len(repeat.get("unchanged_doc_ids",[]))==len(incremental_ids)
        and set(repeat.get("unchanged_doc_ids",[]))==incremental_ids
        and metadata.get("history_hash_before_repeat")==metadata.get("history_hash_after_repeat")==digest(pipeline._json(history)))
    results={
        "frozen_artifact_hashes":integrity["passed"],
        "initial_document_count":initial["documents"]==expected_initial,
        "incremental_document_count":q["documents"]==len(docs),
        "all_sources_present":set(q["doc_ids"])==set(reference_texts),
        "source_text_unchanged":all(r["text"]==reference_texts[r["doc_id"]] for r in current),
        "cross_document_links_exist":q["cross_document_entity_count"]>0,
        "structural_checks":validation["structural_passed"],
        "evidence_review_coverage":review_coverage,
        "evidence_review_replay_match":review_replay_match,
        "injection_query_changed":target_type(initial)==lesson["correct_type"] and target_type(injected)==lesson["injected_type"],
        "correction_query_restored":target_type(corrected)==lesson["correct_type"] and target_type(q)==lesson["correct_type"],
        "revision_history_preserved":len(versions)==3 and [v["kind"] for v in versions]==["import","teaching_injection","correction"],
        "history_versions":history_versions,
        "history_hashes":history_hashes,
        "history_relation_transition":history_transition,
        "repeat_import_idempotent":repeat_unchanged,
        "same_paper_relations_retained":corrected["relation_count"]==initial["relation_count"],
        "new_paper_relations_added":q["relation_count"]>corrected["relation_count"],
    }
    report={"passed":all(results.values()),"checks":results,"documents":q["documents"],
            "entity_mentions":q["entity_mentions"],"relations":q["relation_count"],
            "cross_document_entities":q["cross_document_entity_count"],"link_status_counts":q["link_status_counts"],
            "api_calls_in_replay":0,"scientific_review_complete":False,
            "pending_review_items":len(validation["pending_review"]),
            "note":"通过表示流程和已声明验收成立；不表示所有模型关系或上下文已获专家确认。"}
    if not report["passed"]: raise ValueError("验收未通过: "+json.dumps(report,ensure_ascii=False))
    return report
