"""Run eight frozen text-role checks only; no answer generation or quality scoring."""
import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from sec_rag.evaluation.four_methods import classify_answer, split_answer
from sec_rag.evaluation.ollama_client import OllamaJudge
from sec_rag.evaluation.common import write_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline',action='store_true',help='Validate fixtures and source provenance without model calls')
    parser.add_argument('--workers',type=int,choices=(1,2),default=1)
    args=parser.parse_args()
    fixture=ROOT/'configs/evaluation_classification_checks.json'
    data=json.loads(fixture.read_text(encoding='utf8'))
    for case in data['cases']:
        source=ROOT/case['source']
        if hashlib.sha256(source.read_bytes()).hexdigest()!=case['source_sha256']:
            raise ValueError(f"Source changed: {case['id']}")
        if len(split_answer(case['answer']))!=len(case['expected_kinds']):
            raise ValueError(f"Unit count changed: {case['id']}")
    if args.offline:
        print(f"Validated {len(data['cases'])} fixed cases; no model calls.")
        return
    judge=OllamaJudge()  # Deliberately no cache: this checks fresh model behavior.
    judge.check()
    out=ROOT/'storage/experiments/evaluation/diagnostics/classification'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    write_json(out/'input_snapshot.json',data)
    print(f'Output: {out}',flush=True)
    rows=[]
    for case in data['cases']:
        started=time.perf_counter()
        record={'case':case,'model_digest':judge.model_digest}
        try:
            trace=classify_answer(judge,case['answer'],workers=args.workers)
            parsed=trace['parsed']
            passed=parsed['kinds']==case['expected_kinds'] and parsed['refusal']==case['expected_refusal']
            record.update(trace=trace,status='pass' if passed else 'mismatch')
        except Exception as exc:
            record.update(status='failed',error=str(exc),trace=getattr(exc,'trace',None))
        record['elapsed_seconds']=time.perf_counter()-started
        write_json(out/(case['id']+'.json'),record)
        rows.append({'id':case['id'],'status':record['status'],'elapsed_seconds':record['elapsed_seconds']})
        print(case['id'],record['status'],flush=True)
    write_json(out/'summary.json',{'checks':rows,'pass_count':sum(r['status']=='pass' for r in rows),'total':len(rows),
        'interpretation':'Regression checks only; not clinical accuracy or method performance.'})
    print(f"Passed {sum(r['status']=='pass' for r in rows)}/{len(rows)}; see {out}")


if __name__=='__main__':main()
