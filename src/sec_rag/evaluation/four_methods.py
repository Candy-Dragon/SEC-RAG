"""Fair full-answer evaluation with per-call caches and resumable run records."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from .ollama_client import OllamaJudge
from .common import ROOT, PILOT, PROMPTS, check_prompts, validate_binary_list, validate_citation_set_support, write_json

METHODS = ("llm_only", "traditional_rag", "prompt_constrained_rag", "sec_rag")
METRICS = ("guideline_faithfulness", "citation_recall")


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def mean(values):
    return sum(values)/len(values) if values else None


def check_inputs(source_dir, qids, methods):
    """Fail before inference if selected answers or citation provenance are missing."""
    check_prompts()
    hashes={}
    for qid in qids:
        qdir=source_dir/"questions"/qid
        retrieval_path=qdir/"01_retrieval.json"
        retrieval=read(retrieval_path)
        question=retrieval["input"]["question"]
        chunks=retrieval["retrieval_results"]
        chunk_ids={c["chunk_id"] for c in chunks}
        if not chunks or len(chunk_ids)!=len(chunks):
            raise ValueError(f"{qid}: empty or duplicate retrieval")
        for method in methods:
            path=qdir/"06_final_answer.json" if method=="sec_rag" else qdir/"baselines"/f"{method}.json"
            data=read(path)
            if data.get("status")!="completed":raise ValueError(f"{qid}/{method}: generation incomplete")
            answer=data["final_answer"]["answer"] if method=="sec_rag" else data["record"]["answer"]
            actual_question=data.get("input",{}).get("question") if method=="sec_rag" else data["record"].get("question")
            if actual_question!=question or not isinstance(answer,str) or not answer.strip():
                raise ValueError(f"{qid}/{method}: question mismatch or empty answer")
            if method=="sec_rag":
                for evidence in data["approved_evidence"]:
                    if evidence["source_chunk_id"] not in chunk_ids:
                        raise ValueError(f"{qid}: citation source chunk missing")
            hashes[f"{qid}/{method}"]=hashlib.sha256(path.read_bytes()+retrieval_path.read_bytes()).hexdigest()
    return hashes


def split_answer(answer, split_contrast=True):
    """Verbatim sentence/line units; separate a medical clause from a contrastive evidence gap.

    This is a common sentence-level proxy, not semantic atomic-claim extraction.
    Do not split decimal dots, numeric ranges, or medical inequalities.
    """
    pattern = r'.*?(?:[。！？!?][”’\"\']?(?:[ \t]*\[[^\]\r\n]+\])*|[\r\n]+|$)'
    units = []
    # This boundary is structural: a contrastive clause explicitly starts with
    # "but [the evidence] does not specify/provide/cover". Keep both sides in
    # the source answer with exact offsets. Do not infer a medical label here.
    contrast = re.compile(r'但(?:未明确|未提供|没有|无法|尚无|未覆盖)')
    for match in re.finditer(pattern, answer, re.S):
        raw=match.group()
        boundaries=[0]+[m.start() for m in contrast.finditer(raw) if m.start()>0 and split_contrast]+[len(raw)]
        for left,right in zip(boundaries,boundaries[1:]):
            fragment=raw[left:right]
            text=fragment.strip()
            if not text: continue
            start=match.start()+left+len(fragment)-len(fragment.lstrip())
            end=start+len(text)
            refs=[]
            for bracket in re.findall(r'\[([^\]]+)\]',text):
                parts=re.split(r'[,，、;；\s]+',bracket.strip())
                if parts and all(re.fullmatch(r'(?:E\d+|证据\d+)',part) for part in parts):
                    refs.extend(parts)
            units.append({"id":f"C{len(units)+1}","text":text,"start":start,"end":end,"citations":list(dict.fromkeys(refs))})
    return units


def classification_schema(count):
    return {"type":"object","properties":{
        "kinds":{"type":"array","items":{"type":"string","enum":["medical","evidence_boundary","boundary","other"]},"minItems":count,"maxItems":count}},"required":["kinds"],"additionalProperties":False}


def validate_classification(value, units):
    if not isinstance(value,dict) or not isinstance(value.get("kinds"),list) or len(value["kinds"])!=len(units):
        raise ValueError("kinds must classify every input unit in order")
    if any(k not in ("medical","evidence_boundary","boundary","other") for k in value["kinds"]):
        raise ValueError("invalid kind")
    refusal="evidence_boundary" in value["kinds"] and "medical" not in value["kinds"]
    return {"kinds":value["kinds"],"refusal":refusal,
        "full_refusal_due_to_evidence":refusal,
        "claims":[dict(unit,kind=kind) for unit,kind in zip(units,value["kinds"])]}


def classify_answer(judge, answer, workers=1, split_contrast=True):
    units=split_answer(answer, split_contrast=split_contrast)
    if not units:
        return {"status":"completed","source":"empty_answer","parsed":validate_classification({"kinds":[]},[])}
    # Use a stable local ID so identical sentences can share cached judgments.
    # The model sees one unit only; assemble the original IDs after classification.
    def classify_one(unit):
        local=dict(unit,id="C1")
        return judge.call_json(ROOT/"configs/prompts/evaluation/00_classify_units.txt",
            {"units":[{"id":"C1","text":unit["text"]}]},
            lambda v:validate_classification(v,[local]),schema=classification_schema(1))
    results=[]
    errors=[]
    def run_one(unit):
        try:
            return {"unit_id":unit["id"],"status":"completed","trace":classify_one(unit)}
        except Exception as exc:
            return {"unit_id":unit["id"],"status":"failed","error":str(exc),"trace":getattr(exc,"trace",None)}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results=list(executor.map(run_one,units))
    errors=[r for r in results if r["status"]=="failed"]
    trace={"policy":"independent_units_v1","unit_traces":results,"status":"failed" if errors else "completed"}
    if errors:
        from .ollama_client import LocalJudgeError
        raise LocalJudgeError("Independent unit classification failed",trace)
    kinds=[r["trace"]["parsed"]["kinds"][0] for r in results]
    trace["parsed"]=validate_classification({"kinds":kinds},units)
    return trace


def validate_statements(value, sentences):
    rows=value.get("statements") if isinstance(value,dict) else None
    if not isinstance(rows,list) or not rows:
        raise ValueError("nonempty statements required for medical sentences")
    expected={c["id"] for c in sentences}
    sources={c["id"]:c["text"] for c in sentences}
    seen=set()
    for i,row in enumerate(rows,1):
        if not isinstance(row,dict) or row.get("id")!=f"S{i}" or row.get("source_sentence_id") not in expected:
            raise ValueError("invalid statement ID or source sentence")
        if not isinstance(row.get("text"),str) or not row["text"].strip():
            raise ValueError("empty statement")
        quote=row.get("source_quote")
        if not isinstance(quote,str) or not quote.strip() or quote not in sources[row["source_sentence_id"]]:
            raise ValueError("source_quote must be an exact nonempty span of the assigned sentence")
        seen.add(row["source_sentence_id"])
    if seen!=expected:raise ValueError("every medical sentence needs statements")
    return value


def evaluate(judge, question, answer, chunks, evidence, method, needs_trace=None, workers=1):
    traces={"evaluation_unit_policy":"medical_statements_and_full_sentences_v4",
            "input_snapshot":{"question":question,"answer":answer,"contexts":chunks,"citation_sources":evidence}}
    try:
        traces["claim_trace"]=classify_answer(judge,answer,workers=workers,split_contrast=False)
        parsed=traces["claim_trace"]["parsed"]
        sentences=[c for c in parsed["claims"] if c["kind"]=="medical"]
        statements=[]
        labels=[]
        if sentences:
            # Isolate source sentences: excluded text cannot leak back from the full answer.
            traces["statement_trace"]={"policy":"isolated_sentence_with_source_quote_v1","sentence_traces":[]}
            def extract_one(sentence):
                return judge.call_json(PROMPTS/"01_extract_statements.txt",
                    {"sentences":[{"id":sentence["id"],"text":sentence["text"]}]},
                    lambda v:validate_statements(v,[sentence]))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                for sentence, trace in zip(sentences, executor.map(extract_one,sentences)):
                    traces["statement_trace"]["sentence_traces"].append({"sentence_id":sentence["id"],"trace":trace})
                    for item in trace["parsed"]["statements"]:
                        statements.append({**item,"id":f"S{len(statements)+1}"})
            traces["statement_trace"]["parsed"]={"statements":statements}
            traces["faithfulness_trace"]=judge.call_json(PROMPTS/"01_claim_entailment.txt",
                {"question":question,"contexts":[{"id":c["chunk_id"],"text":c["text"]} for c in chunks],
                 "claims":[{"id":c["id"],"text":c["text"]} for c in statements]},
                lambda v:validate_binary_list(v,"judgments",[c["id"] for c in statements]))
            labels=[x["label"] for x in traces["faithfulness_trace"]["parsed"]["judgments"]]

        def citations_for(sentence):
            refs=sentence["citations"]
            missing=[ref for ref in refs if ref not in evidence]
            row={"sentence_id":sentence["id"],"text":sentence["text"],"citation_ids":refs,"missing_ids":missing}
            if not refs or missing:
                return dict(row,combined_support=False,reason="missing_or_invalid_citation")
            citations=[{"id":ref,"text":evidence[ref]} for ref in refs]
            trace=judge.call_json(ROOT/"configs/prompts/evaluation/02_citation_sentence_support.txt",
                {"claim_id":sentence["id"],"claim":sentence["text"],"citations":citations},validate_citation_set_support)
            return dict(row,combined_support=trace["parsed"]["supported"],trace=trace)

        citation_rows=[]
        if method!="llm_only":
            with ThreadPoolExecutor(max_workers=workers) as executor:
                # Append as results arrive in order so completed decisions survive later failure.
                for row in executor.map(citations_for,sentences):
                    citation_rows.append(row)
                    traces["citation_judgments"]=citation_rows
        traces["citation_judgments"]=citation_rows
        return {"status":"completed","answer":answer,**traces,"result":{
            "method":method,"guideline_faithfulness":mean(labels),
            "citation_recall":mean([r["combined_support"] for r in citation_rows]),
            "faithfulness_supported":sum(labels),"faithfulness_total":len(labels),
            "citation_supported_sentences":sum(r["combined_support"] for r in citation_rows),
            "citation_total_sentences":len(citation_rows),
            "claim_count":len(statements),"medical_sentence_count":len(sentences),
            "answer_characters":len(answer),"has_medical_content":bool(sentences),
            "full_refusal_due_to_evidence":parsed["full_refusal_due_to_evidence"]}}
    except Exception as exc:
        return {"status":"failed","answer":answer,**traces,"error":str(exc),"judge_trace":getattr(exc,"trace",None)}


def summarize(records):
    table=[]
    for method in dict.fromkeys(r["method"] for r in records):
        subset=[r for r in records if r["method"]==method]
        if not subset:continue
        good=[r["result"] for r in subset if r["status"]=="completed"]
        row={"method":method,"total_questions":len(subset),"completed":len(good),"failed":len(subset)-len(good)}
        for metric in METRICS:
            values=[r[metric] for r in good if r[metric] is not None]
            row[metric]=mean(values) if values else ("Failed" if not good else "N/A")
            row[metric+"_valid_n"]=len(values)
        # Failures are not classified as refusals; rates explicitly use completed evaluations.
        row["medical_content_rate"]=mean([r["has_medical_content"] for r in good]) if good else "Failed"
        row["evidence_refusal_rate"]=mean([r["full_refusal_due_to_evidence"] for r in good]) if good else "Failed"
        row["behavior_rate_denominator"]=len(good)
        row["medical_answer_count"]=sum(r["has_medical_content"] for r in good)
        row["full_evidence_refusal_count"]=sum(r["full_refusal_due_to_evidence"] for r in good)
        table.append(row)
    return table


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qid",action="append")
    parser.add_argument("--method",action="append",help="Method name; defaults to the source experiment's registered methods")
    parser.add_argument("--resume",type=Path)
    parser.add_argument("--workers",type=int,choices=(1,2),default=1)
    parser.add_argument("--check-only",action="store_true",help="Validate all selected inputs without contacting any model")
    parser.add_argument("--source-dir",type=Path,default=PILOT,help="Directory containing questions/<qid> results for all four methods")
    parser.add_argument("--output-base",type=Path,default=ROOT/"storage/experiments/evaluation/pilot/four-methods-v4")
    args=parser.parse_args()
    source_dir=args.source_dir.resolve()
    experiment_manifest=source_dir/"experiment_manifest.json"
    default_methods=read(experiment_manifest)["config"]["methods"] if experiment_manifest.exists() else list(METHODS)
    if args.method and any(not re.fullmatch(r"[A-Za-z0-9_-]+", name) for name in args.method):
        raise ValueError("Invalid method name")
    base=args.output_base.resolve()
    out=args.resume.resolve() if args.resume else base/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if args.resume and not (out/"run_manifest.json").exists():raise ValueError("Resume requires a v4 run directory")
    if args.resume:
        previous=read(out/"run_manifest.json")
        if previous.get("version")!=4:raise ValueError("Resume requires version 4")
        if args.qid or args.method:raise ValueError("Resume uses saved selection")
        if str(source_dir)!=previous["source_dir"]:raise ValueError("Resume source directory changed")
        selected_qids=previous["qids"];selected_methods=previous["methods"]
    else:
        selected_qids=sorted(p.name for p in (source_dir/"questions").iterdir() if p.is_dir() and (not args.qid or p.name in args.qid))
        selected_methods=args.method or default_methods
        if not selected_qids:raise ValueError("No questions selected")
        if args.qid and set(args.qid)-set(selected_qids):raise ValueError("Requested question not found")
    source_hashes=check_inputs(source_dir,selected_qids,selected_methods)
    if args.resume and previous.get("source_hashes")!=source_hashes:raise ValueError("Inputs changed; start a new run")
    if args.check_only:
        print(json.dumps({"inputs_valid":True,"question_count":len(selected_qids),"answer_count":len(source_hashes),"model_called":False,"source_dir":str(source_dir)},ensure_ascii=False))
        return
    # Keep the cache path short on Windows. A UUID-suffixed temporary cache
    # filename can exceed MAX_PATH beneath the nested development output.
    cache_root=ROOT/"storage/experiments/evaluation/_cache"
    judge=OllamaJudge(cache_dir=cache_root)
    judge.check()
    source_files=list((ROOT/"src/sec_rag/evaluation").glob("*.py"))+list(PROMPTS.glob("*.txt"))
    fingerprint=hashlib.sha256(b"".join(p.read_bytes() for p in sorted(source_files))+str(judge.model_digest).encode()).hexdigest()
    judge.cache_dir=cache_root/fingerprint
    if args.resume:
        manifest=read(out/"run_manifest.json")
        if manifest["fingerprint"]!=fingerprint:raise ValueError("Code, prompts or judge changed; start a new run")
        if args.qid or args.method:raise ValueError("Resume uses the saved question and method selection")
        qids=manifest["qids"];methods=manifest["methods"]
    else:
        qids=sorted(p.name for p in (source_dir/"questions").iterdir() if p.is_dir() and (not args.qid or p.name in args.qid))
        methods=args.method or default_methods
        if not qids:raise ValueError("No questions selected")
        manifest={"version":4,"unit_policy":"medical_statements_and_full_sentences_v4","fingerprint":fingerprint,"qids":qids,"methods":methods,"model_digest":judge.model_digest,"model":judge.model,"source_dir":str(source_dir),"source_hashes":source_hashes,"metrics":list(METRICS),"implementation":"Published definitions adapted to medical statements; not official ragas package execution"}
        write_json(out/"run_manifest.json",manifest)
        for source_file in source_files:
            snapshot=out/"implementation_snapshot"/source_file.relative_to(ROOT)
            snapshot.parent.mkdir(parents=True,exist_ok=True)
            snapshot.write_bytes(source_file.read_bytes())
        (out/"implementation_snapshot"/"EVALUATION_METRICS_SPEC.md").write_bytes((ROOT/"docs/evaluation.md").read_bytes())
    if args.resume and manifest.get("source_dir",str(PILOT.resolve()))!=str(source_dir):
        raise ValueError("Resume source directory changed")
    print(f"Output: {out}",flush=True)
    records=[]
    for qid in qids:
        qdir=source_dir/"questions"/qid
        ret=read(qdir/"01_retrieval.json");question=ret["input"]["question"];chunks=ret["retrieval_results"]
        for method in methods:
            started=time.perf_counter()
            source=qdir/"06_final_answer.json" if method=="sec_rag" else qdir/"baselines"/f"{method}.json"
            source_hash=hashlib.sha256(source.read_bytes()+(qdir/"01_retrieval.json").read_bytes()).hexdigest()
            path=out/"questions"/qid/f"{method}.json"
            if path.exists():
                saved=read(path)
                if saved.get("source_hash")!=source_hash:raise ValueError("Source changed; start a new run")
                if saved["status"]=="completed":
                    records.append(saved);print(f"{qid} {method}: resumed",flush=True);continue
            data=read(source)
            if method=="sec_rag":
                answer=data["final_answer"]["answer"]
                by_chunk={c["chunk_id"]:c["text"] for c in chunks}
                evidence={e["evidence_id"]:{"quoted_text":e["evidence_text"],
                    "source_context":by_chunk[e["source_chunk_id"]],
                    "source_chunk_id":e["source_chunk_id"]} for e in data["approved_evidence"]}
            else:
                answer=data["record"]["answer"]
                evidence={f"证据{i}":c["text"] for i,c in enumerate(chunks,1)}
            try:
                record=evaluate(judge,question,answer,chunks,evidence,method,workers=args.workers)
            except Exception as exc:
                record={"status":"failed","error":str(exc),"judge_trace":getattr(exc,"trace",None)}
            record.update({"qid":qid,"method":method,"source_hash":source_hash,"elapsed_seconds":time.perf_counter()-started})
            write_json(path,record);records.append(record)
            print(f"{qid} {method}: {record['status']}",flush=True)
    table=summarize(records)
    with (out/"main_quality_evidence_table.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(table[0]));writer.writeheader();writer.writerows(table)
    write_json(out/"summary.json",{"table":table,"completed":sum(r["status"]=="completed" for r in records),"total":len(records)})
    comparison=[]
    for qid in qids:
        for record in [r for r in records if r["qid"]==qid]:
            comparison.append({"qid":qid,"method":record["method"],"status":record["status"],
                "answer":record.get("answer",""),**{m:record.get("result",{}).get(m) for m in METRICS},
                "error":record.get("error","")})
    with (out/"same_question_comparison.csv").open("w",encoding="utf-8-sig",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=["qid","method","status","answer",*METRICS,"error"])
        writer.writeheader();writer.writerows(comparison)
    print(f"Saved: {out / 'main_quality_evidence_table.csv'}",flush=True)


if __name__=="__main__":main()
