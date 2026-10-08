from __future__ import annotations

import json
import os
import sys
from functools import partial
from pathlib import Path

from runbook_rag_review.provider import BEDROCK_MODEL_ID, bedrock_response
from runbook_rag_review.verify_model import (
    MODEL_CALL_LIMIT,
    MODEL_OUTPUT_TOKEN_LIMIT,
    MODEL_TIMEOUT_SECONDS,
    run_model_verification,
)


def main() -> int:
    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("artifacts")
    fixture_dir = Path(__file__).parents[1] / "fixtures"
    region = os.environ.get("AWS_REGION", "us-east-1")
    provider_call = partial(
        bedrock_response,
        region=region,
        timeout_seconds=MODEL_TIMEOUT_SECONDS,
        max_output_tokens=MODEL_OUTPUT_TOKEN_LIMIT,
    )
    report = run_model_verification(
        fixture_dir,
        output_dir,
        provider_call=provider_call,
        execution_mode="real_cloud_model",
        model_metadata={
            "provider": "amazon_bedrock",
            "model_id": BEDROCK_MODEL_ID,
            "region": region,
            "endpoint_kind": "managed_cloud",
            "timeout_seconds": MODEL_TIMEOUT_SECONDS,
            "max_output_tokens": MODEL_OUTPUT_TOKEN_LIMIT,
            "max_calls": MODEL_CALL_LIMIT,
            "temperature": 0,
        },
        artifact_stem="bedrock-verification",
        run_id_prefix="bedrock-verification",
    )
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
