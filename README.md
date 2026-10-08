# Runbook RAG Review

[![CI](https://github.com/sranganatha/runbook-rag-review/actions/workflows/ci.yml/badge.svg)](https://github.com/sranganatha/runbook-rag-review/actions/workflows/ci.yml)

A local evaluation of whether answers over versioned operational runbooks are supported by evidence that applies to the caller's team and requested date.

> A citation is not proof of support; the cited passage must justify the answer and apply to the requested scope and version.

## Why this exists

Runbook answers can look trustworthy while citing stale guidance, another team's procedure, an irrelevant passage, or a document instruction that should never be followed. Citation presence alone cannot distinguish those failures from a grounded answer.

Runbook RAG Review is a bounded evaluation project that keeps retrieval, answer generation, support scoring, and human review separate. Its synthetic FinOps corpus makes those failure modes inspectable without private operational data or a cloud account.

## Evaluation workflow

```text
Versioned runbooks
      ↓ validate and index
Authorized scope + as-of date
      ↓ retrieve applicable passages
Typed answer + evidence IDs
      ↓ validate and score support
Versioned reviewer decision
      ↓
Development and holdout report
```

Scope comes from a trusted caller fixture, not question or document text. Old versions remain available for historical questions but are excluded when they do not apply to the requested date. Missing evidence, conflicting current sources, and provider failures remain visible outcomes.

## What's implemented

The current implementation provides:

- Twelve original synthetic runbook records with versions, effective periods, team scope, exact source text, and SHA-256 digests
- Twenty independent labels frozen into eight development and twelve holdout cases
- Supported, historical, absent-evidence, obsolete-guidance, wrong-scope, conflict, and injected-instruction cases
- Python 3.12 standard-library contracts for documents, questions, answer statuses, and review decisions
- Offline checks for fixture counts, digests, exact evidence references, version periods, split identity, and state-dependent review fields
- Deterministic paragraph chunks with exact offsets and content-derived IDs
- Atomic SQLite FTS5 index replacement with corpus and chunking identity
- Ranked lexical retrieval filtered by trusted team scope and requested date
- Scope-only ranking compared with scope-and-version filtering before ranking
- Typed answered, abstained, and conflict outputs with strict evidence ID validation
- Deterministic fixture generation from supplied passages with context, output, and call budgets
- Immutable run snapshots with exact hashed evidence and versioned JSON review history
- Accept, reject, and correct review decisions with stale-answer protection
- Complete fixed-label development and holdout reporting with separate safety metrics
- Local ingest and fixture-backed ask commands with immutable saved runs
- Deterministic offline demo with replay checks and validated feedback export
- Bounded local-model verification with Qwen 2.5 1.5B served by Ollama in Podman
- Optional bounded cloud verification with Amazon Nova Micro through Bedrock

See the [offline evaluation report](artifacts/evaluation.md). It uses deterministic fixture
answers to exercise retrieval and scoring, so it is not evidence of real-model quality.

See the separate [local-model verification report](artifacts/model-verification.md) for
observed Qwen results. Model-contract failures remain visible and are not replaced with
fixture answers.

The [Bedrock verification report](artifacts/bedrock-verification.md) is independently
labeled and records observed Nova Micro results. It is not used by default checks.

## What the fixtures establish

Labels identify required facts and exact source evidence separately from future prompts and provider fixtures. An abstention label cannot contain a hidden expected answer; answered and conflict labels must point to exact text in a known document version. Changing source text without updating its digest fails validation.

The development split exists for later lexical retrieval tuning. The holdout split stays frozen for final reporting, where every case, including failures and abstentions, must be counted.

## Scope

This is a local RAG correctness and review evaluation, not a managed knowledge base, production assistant, vector-database comparison, chat-memory system, fine-tuning pipeline, or deployment project. It uses one SQLite FTS5 index, one local model lane, and one optional cloud comparison lane; default checks remain offline and credential-free.

## Local validation

Clean validation requires Git, Make, and a running Podman machine. No host Python packages are installed:

```bash
git clone https://github.com/sranganatha/runbook-rag-review.git
cd runbook-rag-review
podman info
make test-container
make demo
```

For source development with Python 3.12 already available, `make check`, `make test`, and
`make report` use only the standard library. Expect
`validated 12 documents and 20 questions (8 development, 12 holdout)`. No validation or
report command calls a model or network service.

## Reproducible verification

`make demo` is the account-free verification command. It runs inside Podman with
networking disabled and writes [verification evidence](artifacts/demo.md) plus the
validated [feedback export](artifacts/feedback.json). The command fails unless all seven
checks pass:

- Rebuilding the same corpus produces the same index identity.
- Replaying fixture generation produces the same normalized retrieval and answer.
- Supported evidence produces an answer.
- Obsolete guidance is excluded in favor of the current document version.
- Missing evidence produces an abstention.
- A reviewer correction remains tied to the exact saved answer and evidence.
- A real citation ID with an unsupported claim fails support evaluation.

## Local model verification

Run the separately labeled real-model check through Make and Podman:

```bash
make verify-model
```

The first run downloads the pinned Ollama image and about 986 MB of Qwen model data into
the `runbook-rag-review-ollama-models` Podman volume. Later runs reuse that volume. The
command makes exactly one bounded model call for each of the twenty frozen cases, writes
JSON and Markdown reports under `artifacts/`, and shuts down the Compose stack. It needs
no cloud account, API key, host Python package, or paid inference call. CPU runtime varies
by machine.

The command succeeds when every case is attempted and retrieval safety checks pass.
Answer quality, abstentions, truncation, invalid output, and transport failures remain
measured report outcomes. Default CI does not download or call the model.

## Bedrock model verification

With AWS shared credentials configured for Bedrock access, run the separate cloud lane:

```bash
make verify-bedrock
```

The target builds a cloud-only image with the pinned AWS SDK, mounts `~/.aws` read-only,
and calls `amazon.nova-micro-v1:0` in `us-east-1` by default. Override `AWS_DIR` or
`AWS_REGION` when needed. It makes one paid call per frozen case and writes
`artifacts/bedrock-verification.json` and `.md`. Nova is forced to return the answer
through a schema-backed Converse tool call, and the application still validates every
field and evidence ID.

The Ollama and Bedrock lanes are independent. Neither retries, routes to the other model,
or substitutes fixture output after a failure.

## Local fixture workflow

Build the bundled synthetic corpus index, then ask with scope from a caller fixture:

```bash
python -m runbook_rag_review.cli ingest --index .local/runbooks.db
python -m runbook_rag_review.cli ask \
  --index .local/runbooks.db \
  --store .local/reviews \
  --run-id demo-001 \
  --caller-id caller-fixture-finops \
  --as-of 2026-01-15 \
  --question "What are the monthly budget thresholds?"
```

The ask command uses deterministic fixture generation and saves the exact retrieval and
answer under the explicit run ID. It does not call a model or network service.

## Design reference

- [Release history](CHANGELOG.md)
- [MVP specification](docs/mvp-spec.md)
- [Local model decision](docs/adr/0001-local-ollama-qwen.md)
- [Optional Bedrock comparison](docs/adr/0002-bedrock-nova-micro.md)
