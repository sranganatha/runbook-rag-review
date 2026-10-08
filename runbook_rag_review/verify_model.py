from __future__ import annotations

import json
import os
import sys
import tempfile
from collections.abc import Callable
from dataclasses import asdict
from functools import partial
from pathlib import Path
from typing import Any

from runbook_rag_review.answer import Answer, generate_answer
from runbook_rag_review.contracts import ContractError, validate_fixture_set
from runbook_rag_review.evaluate import evaluate_answer
from runbook_rag_review.index import build_index
from runbook_rag_review.provider import OLLAMA_MODEL_ID, ProviderResponse, ollama_response
from runbook_rag_review.retrieve import RetrievalResult, retrieve

MODEL_CALL_LIMIT = 20
MODEL_OUTPUT_TOKEN_LIMIT = 512
MODEL_TIMEOUT_SECONDS = 120
OLLAMA_IMAGE = "docker.io/ollama/ollama:0.40.0"
OLLAMA_IMAGE_DIGEST = (
    "sha256:2b28812c24b17215d15f8f1c0c2bf939d3b5426ba1e8bea15b046f43d5bd2746"
)
MODEL_MANIFEST_SHA256 = (
    "f2b0a490f661d58f20c4b98e5797ecf55e6e96293a88b71e96e7cc389f658f7e"
)


def run_model_verification(
    fixture_dir: Path,
    output_dir: Path,
    *,
    endpoint: str | None = None,
    provider_call: Callable[[str], ProviderResponse] | None = None,
    k: int = 5,
    execution_mode: str = "real_local_model",
    model_metadata: dict[str, Any] | None = None,
    artifact_stem: str = "model-verification",
    run_id_prefix: str = "model-verification",
) -> dict[str, Any]:
    document_records = json.loads((fixture_dir / "documents.json").read_bytes())
    question_records = json.loads((fixture_dir / "questions.json").read_bytes())
    documents, labels = validate_fixture_set(document_records, question_records)
    if len(labels) > MODEL_CALL_LIMIT:
        raise ContractError("model_call_budget_exceeded", str(len(labels)))
    if provider_call is None:
        if endpoint is None:
            raise ContractError("invalid_provider_endpoint", "Ollama endpoint is required")
        provider_call = partial(
            ollama_response,
            endpoint=endpoint,
            timeout_seconds=MODEL_TIMEOUT_SECONDS,
            max_output_tokens=MODEL_OUTPUT_TOKEN_LIMIT,
        )

    with tempfile.TemporaryDirectory() as temporary_directory:
        index_path = Path(temporary_directory) / "runbooks.db"
        index_digest = build_index(index_path, documents)
        cases = []
        for label in labels:
            provider_responses: list[ProviderResponse] = []

            def capture_provider_response(context_json: str) -> ProviderResponse:
                response = provider_call(context_json)
                provider_responses.append(response)
                return response

            retrieval = retrieve(
                index_path,
                label.question,
                label.authorized_scope,
                label.as_of,
                limit=k,
            )
            case = {
                "case_id": label.case_id,
                "split": label.split,
                "category": label.category,
                "expected_status": label.expected_status.value,
                "question": label.question,
                "retrieval": _retrieval_record(retrieval),
                "safety": _safety(label.as_of.isoformat(), label.authorized_scope, retrieval),
            }
            try:
                answer = generate_answer(
                    f"{run_id_prefix}:{label.case_id}",
                    label.question,
                    retrieval,
                    capture_provider_response,
                    generation_mode="local_model",
                )
            except ContractError as error:
                case["error"] = {"code": error.code, "message": str(error)}
            else:
                case["answer"] = _answer_record(answer)
                case["evaluation"] = evaluate_answer(label, retrieval, answer)
            if provider_responses:
                case["provider_response"] = _provider_record(provider_responses[0])
            cases.append(case)

    report = {
        "schema_version": 1,
        "execution_mode": execution_mode,
        "model": model_metadata or {
            "provider": "ollama",
            "model_id": OLLAMA_MODEL_ID,
            "endpoint_kind": "local_container",
            "timeout_seconds": MODEL_TIMEOUT_SECONDS,
            "max_output_tokens": MODEL_OUTPUT_TOKEN_LIMIT,
            "max_calls": MODEL_CALL_LIMIT,
            "temperature": 0,
            "seed": 7,
            "ollama_image": OLLAMA_IMAGE,
            "ollama_image_digest": OLLAMA_IMAGE_DIGEST,
            "model_manifest_sha256": MODEL_MANIFEST_SHA256,
        },
        "index_digest": index_digest,
        "k": k,
        "provider_calls": len(cases),
        "splits": {
            split: _summarize([case for case in cases if case["split"] == split])
            for split in ("development", "holdout")
        },
        "cases": cases,
    }
    report["run_completed"] = len(cases) == len(labels)
    report["safety_verification_passed"] = all(
        case["safety"]["unauthorized_chunks"] == 0
        and case["safety"]["stale_chunks"] == 0
        for case in cases
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{artifact_stem}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (output_dir / f"{artifact_stem}.md").write_text(
        _markdown(report), encoding="utf-8", newline="\n"
    )
    return report


def _retrieval_record(retrieval: RetrievalResult) -> dict[str, Any]:
    return {
        "query": retrieval.query,
        "authorized_scope": retrieval.authorized_scope,
        "as_of": retrieval.as_of.isoformat(),
        "index_digest": retrieval.index_digest,
        "hits": [asdict(hit) for hit in retrieval.hits],
    }


def _answer_record(answer: Answer) -> dict[str, Any]:
    return {
        "run_id": answer.run_id,
        "status": answer.status.value,
        "claims": [asdict(claim) for claim in answer.claims],
        "reason": answer.reason,
        "generation_mode": answer.generation_mode,
        "model_id": answer.model_id,
        "attempted_calls": answer.attempted_calls,
        "elapsed_ms": answer.elapsed_ms,
        "usage_tokens": answer.usage_tokens,
        "context_chunk_ids": list(answer.context_chunk_ids),
        "limits": asdict(answer.limits),
    }


def _provider_record(response: ProviderResponse) -> dict[str, Any]:
    return {
        "status": response.status.value,
        "output_text": response.output_text,
        "model_id": response.model_id,
        "attempted_calls": response.attempted_calls,
        "elapsed_ms": response.elapsed_ms,
        "usage_tokens": response.usage_tokens,
    }


def _safety(as_of: str, authorized_scope: str, retrieval: RetrievalResult) -> dict[str, int]:
    return {
        "unauthorized_chunks": sum(
            hit.team_scope != authorized_scope for hit in retrieval.hits
        ),
        "stale_chunks": sum(
            hit.effective_from > as_of
            or (hit.effective_to is not None and hit.effective_to < as_of)
            for hit in retrieval.hits
        ),
    }


def _summarize(cases: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [case for case in cases if "evaluation" in case]
    expected_abstentions = sum(
        case["expected_status"] == "abstained" for case in cases
    )
    return {
        "cases": len(cases),
        "completed": len(completed),
        "errors": len(cases) - len(completed),
        "status_matches": {
            "numerator": sum(case["evaluation"]["status_match"] for case in completed),
            "denominator": len(cases),
        },
        "false_answers": {
            "numerator": sum(case["evaluation"]["false_answer"] for case in completed),
            "denominator": expected_abstentions,
        },
        "unauthorized_chunks": sum(
            case["safety"]["unauthorized_chunks"] for case in cases
        ),
        "stale_chunks": sum(case["safety"]["stale_chunks"] for case in cases),
        "known_usage_tokens": sum(
            case["provider_response"]["usage_tokens"]
            for case in cases
            if case.get("provider_response", {}).get("usage_tokens") is not None
        ),
        "unknown_usage_cases": sum(
            case.get("provider_response", {}).get("usage_tokens") is None
            for case in cases
        ),
    }


def _markdown(report: dict[str, Any]) -> str:
    provider_label = report["model"]["provider"].replace("_", " ").title()
    lines = [
        f"# {provider_label} Model Verification",
        "",
        f"Execution mode: `{report['execution_mode']}`. "
        "Results are observed, not fixture output.",
        "",
        f"Model: `{report['model']['model_id']}` via {provider_label}.",
        "",
        "## Summary",
        "",
        "| Split | Cases | Completed | Errors | Status | False answers | Scope | Stale | Tokens |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for split, metrics in report["splits"].items():
        lines.append(
            f"| {split} | {metrics['cases']} | {metrics['completed']} | "
            f"{metrics['errors']} | {_ratio(metrics['status_matches'])} | "
            f"{_ratio(metrics['false_answers'])} | {metrics['unauthorized_chunks']} | "
            f"{metrics['stale_chunks']} | {metrics['known_usage_tokens']}"
            f"{'+' + str(metrics['unknown_usage_cases']) + ' unknown' if metrics['unknown_usage_cases'] else ''} |"
        )
    lines.extend(
        [
            "",
            f"Run completed: {'yes' if report['run_completed'] else 'no'}.",
            "",
            "Safety verification passed: "
            f"{'yes' if report['safety_verification_passed'] else 'no'}.",
            "",
            "## Per-case results",
            "",
            "| Split | Case | Expected | Actual | Status match | Error |",
            "|---|---|---|---|---|---|",
        ]
    )
    for case in report["cases"]:
        evaluation = case.get("evaluation")
        error = case.get("error")
        lines.append(
            f"| {case['split']} | `{case['case_id']}` | {case['expected_status']} | "
            f"{evaluation['actual_status'] if evaluation else 'error'} | "
            f"{'yes' if evaluation and evaluation['status_match'] else 'no'} | "
            f"{error['code'] if error else ''} |"
        )
    return "\n".join(lines) + "\n"


def _ratio(value: dict[str, int]) -> str:
    return f"{value['numerator']}/{value['denominator']}"


def main() -> int:
    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("artifacts")
    fixture_dir = Path(__file__).parents[1] / "fixtures"
    endpoint = os.environ.get("OLLAMA_URL", "http://ollama:11434")
    report = run_model_verification(fixture_dir, output_dir, endpoint=endpoint)
    print(
        json.dumps(
            {
                "cases": len(report["cases"]),
                "model_id": report["model"]["model_id"],
                "output_dir": str(output_dir),
                "run_completed": report["run_completed"],
                "safety_verification_passed": report["safety_verification_passed"],
            },
            sort_keys=True,
        )
    )
    return 0 if report["run_completed"] and report["safety_verification_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
