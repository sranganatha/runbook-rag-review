# MVP Specification

## 1. Claim

Runbook RAG Review tests one claim:

> A citation is not proof of support; the cited passage must justify the answer and apply to the requested team and date.

The MVP answers questions over versioned synthetic FinOps runbooks, abstains when evidence is absent, reports applicable conflicts, and records reviewer decisions against the exact answer and evidence snapshot.

## 2. Workflow

```text
validate corpus -> build local index -> retrieve authorized current passages
-> generate typed answer -> validate evidence IDs -> evaluate support
-> append versioned review -> report development and holdout results
```

Retrieval and generation remain separate so failures in either layer stay visible.

## 3. Contracts

- A document has an ID, version, effective period, team scope, exact source text, SHA-256 digest, and an original-synthetic-content declaration.
- A question has a case ID, text, trusted caller scope fixture, as-of date, and frozen development or holdout assignment.
- A label has an expected answer status, exact relevant evidence, required facts, and critical applicability constraints.
- A retrieval record has query, configuration, index digest, ordered chunk IDs and scores, and filter context.
- An answer has a run ID, typed status, claims with evidence IDs, and generation mode/configuration.
- A review has answer/run identity, reviewer fixture identity, accept/reject/correct decision, rationale, corrected claims/evidence when required, and a versioned timestamp.

Materially different answer statuses are `answered`, `abstained`, and `conflict`. Review decisions are `accept`, `reject`, and `correct`.

## 4. Trust boundaries

- Caller fixtures supply authorized team scope; question and document text cannot change it.
- Scope and effective-period filters run before generation, and retrieved chunks are checked again at the provider boundary.
- Old versions remain available for historical questions but not current ones.
- Overlapping effective versions of the same document are invalid fixture data unless a labeled case explicitly models a source conflict.
- Document instructions are evidence text, never system policy or authority to call tools, change endpoints, or reveal data.
- Missing retrieval and provider failure cannot fall back to general model knowledge or a fixture answer.

## 5. Corpus and evaluation

The frozen corpus contains twelve original synthetic runbook records and twenty labeled questions: eight development cases and twelve holdout cases. Labels cover supported answers, absent evidence, obsolete guidance, wrong-team passages, conflicting applicable sources, and injected document instructions.

Development cases may tune lexical query and `k`. Holdout cases are counted without exclusions. Final reporting separates retrieval recall, required-fact support, false answers on unanswerable cases, stale/scope violations, citation-ID validity, and review outcomes.

Acceptance requires zero unauthorized chunks, zero fabricated citation IDs, typed no-evidence/conflict handling, and a result for every case. Answer quality is reported as observed rather than hidden by changing labels.

## 6. Implementation slices

1. Versioned corpus, frozen labels, contracts, and offline validation.
2. Paragraph chunks, stable IDs/offsets, atomic SQLite FTS5 index, metadata filtering, and index identity.
3. Fixture generation, answer/evidence validation, budgets, and one explicitly configured model connection.
4. Append-only review workflow with answer/evidence snapshots and stale-version protection.
5. Development-tuned retrieval comparison and complete holdout support report.
6. CLI, offline container verification, bounded model verification, and scripted demo.

Each slice exits with a runnable check. Do not begin later-slice implementation merely to scaffold it.

## 7. Non-goals

No dashboard, chat history, memory service, dynamic chunking study, embeddings/vector store, managed knowledge base, fine-tuning, multiple providers, cloud deployment, enterprise authentication, or private operational data.

## 8. Completion

The default demo must run without an account or API key and show a supported answer, stale-source exclusion, an unsupported-question abstention, a reviewer correction, and a real-but-irrelevant citation failing support evaluation. Model verification is operator-run, bounded, and separately labeled.
