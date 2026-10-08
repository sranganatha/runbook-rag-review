# ADR 0002: Optional Bedrock Nova Micro Comparison

Status: accepted

## Context

The local Qwen lane is credential-free and reproducible, but its small model size limits
answer quality. A separately labeled cloud lane can show whether a managed generative
model improves contract adherence without weakening the local baseline or default offline
checks.

## Decision

Retain the Ollama and Qwen lane and add an optional Amazon Bedrock lane using
`amazon.nova-micro-v1:0`. Use Bedrock Converse in `us-east-1` by default with one call per
frozen case, temperature zero, a 120-second timeout, and a 512-token output limit.

Force Nova Micro to call one `submit_answer` tool whose input follows the answer JSON
schema. Validate the returned tool input again with the same application contract and
evidence-ID checks used by the local lane. Do not retry, fall back, or route between
providers.

Install the pinned `boto3==1.43.97` dependency only in `Containerfile.bedrock`. Mount AWS
shared credentials read-only at runtime. Keep the default container and CI dependency-free,
credential-free, and network-disabled.

## Consequences

The cloud run incurs Bedrock usage charges and requires credentials with
`bedrock:InvokeModel`. Its report is not interchangeable with local evidence because model
identity, region, timing, tokens, and execution mode are preserved separately. The managed
lane offers stronger structured-output performance, while the local lane remains the
portable baseline.
