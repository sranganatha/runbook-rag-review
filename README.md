# Runbook RAG Review

A local evaluation of whether answers over versioned operational runbooks are supported by evidence that applies to the caller's team and requested date.

> A citation is not proof of support; the cited passage must justify the answer and apply to the requested scope and version.

## Why this exists

Runbook answers can look trustworthy while citing stale guidance, another team's procedure, an irrelevant passage, or a document instruction that should never be followed. Citation presence alone cannot distinguish those failures from a grounded answer.

Runbook RAG Review is a bounded evaluation project that will keep retrieval, answer generation, support scoring, and human review separate. Its synthetic FinOps corpus makes those failure modes inspectable without private operational data or a cloud account.

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

Retrieval, answer generation, review persistence, reporting, model calls, and container commands are not implemented in this slice.

## What the fixtures establish

Labels identify required facts and exact source evidence separately from future prompts and provider fixtures. An abstention label cannot contain a hidden expected answer; answered and conflict labels must point to exact text in a known document version. Changing source text without updating its digest fails validation.

The development split exists for later lexical retrieval tuning. The holdout split stays frozen for final reporting, where every case—including failures and abstentions—must be counted.

## Scope

This is a local RAG correctness and review evaluation, not a managed knowledge base, production assistant, vector-database comparison, chat-memory system, fine-tuning pipeline, or deployment project. The complete MVP will use one SQLite FTS5 index and one explicitly selected model connection; default checks will remain offline and credential-free.

## Local validation

Requires Python 3.12 or newer and no third-party packages:

```bash
git clone https://github.com/sranganatha/runbook-rag-review.git
cd runbook-rag-review
python -m unittest discover -s tests -v
python -m runbook_rag_review.validate_fixtures
```

Expect `validated 12 documents and 20 questions (8 development, 12 holdout)`. The validator reads `fixtures/documents.json` and `fixtures/questions.json`; it does not call a model or network service.

## Design reference

- [MVP specification](docs/mvp-spec.md)
