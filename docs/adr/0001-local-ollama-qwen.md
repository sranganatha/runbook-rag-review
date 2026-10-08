# ADR 0001: Local Ollama and Qwen Model Verification

Status: accepted

## Context

The MVP needs one bounded real-model verification path without changing the deterministic,
offline default checks. The path must run through Make and Podman, avoid host dependencies,
preserve failures as typed outcomes, and make no more than one call per frozen case.

Three options were considered:

- Amazon Bedrock Nova Micro is a small hosted generative model, but it needs valid AWS
  credentials and creates an external paid dependency.
- BERT-family encoders are useful for classification and retrieval but do not directly
  produce the structured cited answers required by this evaluation.
- A small instruction model served locally by Ollama is generative, credential-free, and
  fits the existing Podman workflow.

## Decision

Use `qwen2.5:1.5b` through Ollama 0.40.0 for the single real-model verification path.
Pin the Ollama image by digest and record the model manifest digest in every report. Store
model data in a dedicated Podman volume. Send scope-filtered passages through the Ollama
chat API with temperature zero, a fixed seed, a 120-second timeout, and a 512-token output
limit. Validate model JSON and evidence IDs in the application with no retry or fixture
fallback.

The selected Qwen model is an Apache 2.0 licensed 1.5B instruction model. Its Ollama model
download is about 986 MB. The pinned identifiers are:

- Ollama image digest:
  `sha256:2b28812c24b17215d15f8f1c0c2bf939d3b5426ba1e8bea15b046f43d5bd2746`
- Qwen manifest SHA-256:
  `f2b0a490f661d58f20c4b98e5797ecf55e6e96293a88b71e96e7cc389f658f7e`

## Consequences

Verification needs enough local memory for the model and is slower on CPU than hosted
inference. The first run downloads roughly 986 MB. Small-model answer quality is an
observed benchmark result, not a release gate. Scope and version filtering, full case
accounting, and visible contract failures remain release gates. Default CI stays fast,
offline, and model-free.
