"""Config-driven experiment runner; same inputs and retrieval across selected methods."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
from pathlib import Path

from sec_rag.config import settings
from sec_rag.data.adapters import load_questions
from sec_rag.evaluation.common import write_json
from sec_rag.method.artifacts import verify_artifacts, seal_artifacts

BUILTINS = {
    "llm_only": "sec_rag.experiments.llm_only:run_llm_only",
    "traditional_rag": "sec_rag.experiments.traditional_rag:run_traditional_rag",
    "prompt_constrained_rag": "sec_rag.experiments.prompt_constrained_rag:run_prompt_constrained_rag",
    "sec_rag": None,
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def project_path(value):
    path = (settings.root / value).resolve()
    if not path.is_relative_to(settings.root.resolve()):
        raise ValueError("Experiment paths must be inside the checkout for portable provenance")
    return path


def resolve_method(name, plugins):
    target = BUILTINS.get(name) if name in BUILTINS else plugins.get(name)
    if name == "sec_rag":
        return None
    if not isinstance(target, str) or ":" not in target:
        raise ValueError(f"Unregistered method: {name}")
    module, function = target.split(":", 1)
    value = getattr(importlib.import_module(module), function)
    if not callable(value):
        raise ValueError(f"Method is not callable: {name}")
    return value


def prepare(config):
    from sec_rag.method.components import resolve_components
    resolve_components(config.get("components"))
    dataset = config["dataset"]
    source = project_path(dataset["path"])
    rows = load_questions(source, format=dataset["format"], columns=dataset["columns"], dataset=dataset["name"])
    knowledge = project_path(config["knowledge_base"])
    corpus = knowledge / "indexes/bm25/corpus.jsonl"
    manifest = knowledge / "indexes/bm25/index_manifest.json"
    corpus_hash = hashlib.sha256(corpus.read_bytes()).hexdigest()
    if read(manifest)["corpus_sha256"] != corpus_hash:
        raise ValueError("Knowledge corpus does not match its manifest")
    scope_path = project_path(config["scope_config"])
    allowed = set(read(scope_path)["included_diseases"])
    top_n = config.get("top_n", 5)
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n < 1:
        raise ValueError("top_n must be a positive integer")
    counts = {}
    for line in corpus.read_text(encoding="utf-8").splitlines():
        if line.strip():
            chunk = json.loads(line)
            for key in ("chunk_id", "document_id", "disease", "source_file", "page_start", "page_end", "text", "tokens"):
                if key not in chunk:
                    raise ValueError(f"Corpus record missing {key}")
            counts[chunk["disease"]] = counts.get(chunk["disease"], 0) + 1
    for row in rows:
        domain = row["disease_scope"]
        if domain not in allowed or counts.get(domain, 0) < top_n:
            raise ValueError(f"Domain {domain}: outside scope or fewer than top_n chunks")
    names = config["methods"]
    if not isinstance(names, list) or not names or len(set(names)) != len(names):
        raise ValueError("methods must be a nonempty unique list")
    plugins = config.get("plugins", {})
    if set(plugins) & set(BUILTINS):
        raise ValueError("Plugins cannot replace built-in method names")
    for name in names:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name) or (name not in BUILTINS and name not in plugins):
            raise ValueError(f"Invalid/unregistered method: {name}")
    output = project_path(config["output_dir"])
    if not output.is_relative_to((settings.root / "storage/experiments").resolve()):
        raise ValueError("output_dir must be under storage/experiments/")
    # Include all active source/config bytes so resumed runs cannot mix implementations.
    files = sorted(p for folder in ("src", "configs") for p in (settings.root / folder).rglob("*")
                   if p.is_file() and p.suffix in (".py", ".json", ".txt"))
    hashes = {p.relative_to(settings.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    for path in (source, corpus, manifest, scope_path):
        hashes[path.relative_to(settings.root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    identity = {"config": config, "files": hashes, "model": settings.model_name,
                "temperature": settings.model_temperature, "base_url": settings.model_base_url,
                "max_output_tokens": settings.model_max_output_tokens}
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return rows, output, identity, fingerprint


def run(config, *, check_only=False):
    rows, output, identity, fingerprint = prepare(config)
    if check_only:
        return {"inputs_valid": True, "questions": len(rows), "methods": config["methods"], "model_called": False}
    path = output / "experiment_manifest.json"
    if path.exists():
        if read(path)["fingerprint"] != fingerprint:
            raise ValueError("Input/config/code changed; choose a new output_dir")
    elif output.exists() and any(output.iterdir()):
        raise ValueError("Output directory already belongs to another experiment")
    methods = {name: resolve_method(name, config.get("plugins", {})) for name in config["methods"]}
    write_json(path, {"fingerprint": fingerprint, **identity})
    write_json(output / "input_questions.json", rows)
    old_kb, old_scope = settings.knowledge_base_root, settings.experiment_scope_path
    settings.knowledge_base_root = config["knowledge_base"]
    settings.experiment_scope_path = config["scope_config"]
    progress = []
    try:
        from sec_rag.method.components import resolve_components, execute
        resolved = resolve_components(config.get("components"))
        from sec_rag.method.runner import run_question
        for row in rows:
            qdir = output / "questions" / row["qid"]
            verify_artifacts(qdir)
            retrieval_path = qdir / "01_retrieval.json"
            if not retrieval_path.exists():
                execute("01_retrieval", resolved, {
                    "question": row["question"], "question_id": row["qid"], "source_dataset": row["source_dataset"],
                    "disease_scope": row["disease_scope"], "top_n": config.get("top_n", 5),
                }, retrieval_path)
                seal_artifacts(qdir)
            retrieval = read(retrieval_path)["retrieval_results"]
            for name, function in methods.items():
                destination = qdir / "06_final_answer.json" if name == "sec_rag" else qdir / "baselines" / f"{name}.json"
                if destination.exists() and read(destination).get("status") == "completed":
                    progress.append({"qid": row["qid"], "method": name, "status": "completed", "resumed": True})
                    continue
                if destination.exists():
                    attempts = destination.parent / "failed_attempts"
                    attempts.mkdir(parents=True, exist_ok=True)
                    digest = hashlib.sha256(destination.read_bytes()).hexdigest()[:16]
                    (attempts / f"{destination.stem}_{digest}.json").write_bytes(destination.read_bytes())
                try:
                    if name == "sec_rag":
                        run_question(question=row["question"], question_id=row["qid"], source_dataset=row["source_dataset"],
                                     disease_scope=row["disease_scope"], top_n=config.get("top_n", 5), output_dir=qdir, components=config.get("components"))
                        if not destination.exists() or read(destination).get("status") != "completed":
                            raise ValueError("SEC-RAG returned without a completed final answer artifact")
                    else:
                        record = function(row["question"]) if name == "llm_only" else function(
                            row["question"], top_k=len(retrieval), disease=row["disease_scope"], retrieval=retrieval)
                        if record.get("question") != row["question"] or not isinstance(record.get("answer"), str) or not record["answer"].strip():
                            raise ValueError("Method must return original question and nonempty answer")
                        write_json(destination, {"status": "completed", "qid": row["qid"], "method": name, "record": record})
                    progress.append({"qid": row["qid"], "method": name, "status": "completed"})
                except Exception as exc:
                    failure = {"qid": row["qid"], "method": name, "status": "failed", "error": str(exc)}
                    if name != "sec_rag":
                        write_json(destination, {**failure, "record": getattr(exc, "record", None)})
                    progress.append(failure)
                seal_artifacts(qdir)
                write_json(output / "progress.json", {"results": progress})
                print(f"{row['qid']} {name}: {progress[-1]['status']}", flush=True)
    finally:
        settings.knowledge_base_root, settings.experiment_scope_path = old_kb, old_scope
        write_json(output / "progress.json", {"results": progress})
    return {"questions": len(rows), "completed": sum(p["status"] == "completed" for p in progress),
            "failed": sum(p["status"] == "failed" for p in progress), "output": str(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    result = run(read(args.experiment), check_only=args.check_only)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result.get("failed", 0) > 0)
