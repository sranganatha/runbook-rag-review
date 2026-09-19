# Offline Evaluation Report

Execution mode: `deterministic_fixture`. This is not real-model quality evidence.

Fixed retrieval depth: `k=5`. Development tuning performed: none.

## Summary

| Configuration | Split | Cases | Retrieval recall | Required facts | Citation IDs | Claims | Status | False answers | Scope | Stale |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `scope_only_then_applicability` | development | 8 | 4/6 | 4/7 | 8/8 | 8/8 | 4/8 | 3/3 | 0 | 0 |
| `scope_only_then_applicability` | holdout | 12 | 14/14 | 6/21 | 12/12 | 12/12 | 9/12 | 2/2 | 0 | 0 |
| `scope_and_version_before_ranking` | development | 8 | 4/6 | 4/7 | 8/8 | 8/8 | 4/8 | 3/3 | 0 | 0 |
| `scope_and_version_before_ranking` | holdout | 12 | 14/14 | 6/21 | 12/12 | 12/12 | 9/12 | 2/2 | 0 | 0 |

## Isolated negative control

The unscoped control is retrieval-only and made zero provider calls.

Unauthorized chunks: 15. Stale chunks: 9.

## Per-case results

| Configuration | Split | Case | Expected | Actual | Recall | Facts | Citation IDs | Claims | False answer |
|---|---|---|---|---|---:|---:|---:|---:|---|
| `scope_only_then_applicability` | development | `dev-01-current-tag-deadline` | answered | answered | 1/1 | 1/1 | 1/1 | 1/1 | no |
| `scope_only_then_applicability` | development | `dev-02-historical-tag-escalation` | answered | answered | 0/1 | 0/1 | 1/1 | 1/1 | no |
| `scope_only_then_applicability` | development | `dev-03-stale-tag-guidance` | answered | answered | 1/1 | 1/1 | 1/1 | 1/1 | no |
| `scope_only_then_applicability` | development | `dev-04-wrong-team-pipeline` | abstained | answered | 0/0 | 0/0 | 1/1 | 1/1 | yes |
| `scope_only_then_applicability` | development | `dev-05-absent-contract-negotiation` | abstained | answered | 0/0 | 0/0 | 1/1 | 1/1 | yes |
| `scope_only_then_applicability` | development | `dev-06-anomaly-paging-conflict` | conflict | answered | 1/2 | 0/2 | 1/1 | 1/1 | no |
| `scope_only_then_applicability` | development | `dev-07-compute-schedule` | answered | answered | 1/1 | 2/2 | 1/1 | 1/1 | no |
| `scope_only_then_applicability` | development | `dev-08-injected-upload-instruction` | abstained | answered | 0/0 | 0/0 | 1/1 | 1/1 | yes |
| `scope_only_then_applicability` | holdout | `holdout-01-rightsizing-threshold` | answered | answered | 1/1 | 0/3 | 1/1 | 1/1 | no |
| `scope_only_then_applicability` | holdout | `holdout-02-rightsizing-change` | answered | answered | 1/1 | 3/3 | 1/1 | 1/1 | no |
| `scope_only_then_applicability` | holdout | `holdout-03-commitment-sizing` | answered | answered | 2/2 | 0/2 | 1/1 | 1/1 | no |
| `scope_only_then_applicability` | holdout | `holdout-04-refund-accounting` | answered | answered | 1/1 | 0/3 | 1/1 | 1/1 | no |
| `scope_only_then_applicability` | holdout | `holdout-05-storage-archive` | answered | answered | 2/2 | 0/3 | 1/1 | 1/1 | no |
| `scope_only_then_applicability` | holdout | `holdout-06-budget-thresholds` | answered | answered | 2/2 | 0/2 | 1/1 | 1/1 | no |
| `scope_only_then_applicability` | holdout | `holdout-07-data-platform-authorized` | answered | answered | 1/1 | 2/2 | 1/1 | 1/1 | no |
| `scope_only_then_applicability` | holdout | `holdout-08-historical-tag-report` | answered | answered | 1/1 | 1/1 | 1/1 | 1/1 | no |
| `scope_only_then_applicability` | holdout | `holdout-09-wrong-scope-job-pause` | abstained | answered | 0/0 | 0/0 | 1/1 | 1/1 | yes |
| `scope_only_then_applicability` | holdout | `holdout-10-absent-deletion-approval` | abstained | answered | 0/0 | 0/0 | 1/1 | 1/1 | yes |
| `scope_only_then_applicability` | holdout | `holdout-11-anomaly-conflict` | conflict | answered | 2/2 | 0/1 | 1/1 | 1/1 | no |
| `scope_only_then_applicability` | holdout | `holdout-12-injected-approval` | answered | answered | 1/1 | 0/1 | 1/1 | 1/1 | no |
| `scope_and_version_before_ranking` | development | `dev-01-current-tag-deadline` | answered | answered | 1/1 | 1/1 | 1/1 | 1/1 | no |
| `scope_and_version_before_ranking` | development | `dev-02-historical-tag-escalation` | answered | answered | 0/1 | 0/1 | 1/1 | 1/1 | no |
| `scope_and_version_before_ranking` | development | `dev-03-stale-tag-guidance` | answered | answered | 1/1 | 1/1 | 1/1 | 1/1 | no |
| `scope_and_version_before_ranking` | development | `dev-04-wrong-team-pipeline` | abstained | answered | 0/0 | 0/0 | 1/1 | 1/1 | yes |
| `scope_and_version_before_ranking` | development | `dev-05-absent-contract-negotiation` | abstained | answered | 0/0 | 0/0 | 1/1 | 1/1 | yes |
| `scope_and_version_before_ranking` | development | `dev-06-anomaly-paging-conflict` | conflict | answered | 1/2 | 0/2 | 1/1 | 1/1 | no |
| `scope_and_version_before_ranking` | development | `dev-07-compute-schedule` | answered | answered | 1/1 | 2/2 | 1/1 | 1/1 | no |
| `scope_and_version_before_ranking` | development | `dev-08-injected-upload-instruction` | abstained | answered | 0/0 | 0/0 | 1/1 | 1/1 | yes |
| `scope_and_version_before_ranking` | holdout | `holdout-01-rightsizing-threshold` | answered | answered | 1/1 | 0/3 | 1/1 | 1/1 | no |
| `scope_and_version_before_ranking` | holdout | `holdout-02-rightsizing-change` | answered | answered | 1/1 | 3/3 | 1/1 | 1/1 | no |
| `scope_and_version_before_ranking` | holdout | `holdout-03-commitment-sizing` | answered | answered | 2/2 | 0/2 | 1/1 | 1/1 | no |
| `scope_and_version_before_ranking` | holdout | `holdout-04-refund-accounting` | answered | answered | 1/1 | 0/3 | 1/1 | 1/1 | no |
| `scope_and_version_before_ranking` | holdout | `holdout-05-storage-archive` | answered | answered | 2/2 | 0/3 | 1/1 | 1/1 | no |
| `scope_and_version_before_ranking` | holdout | `holdout-06-budget-thresholds` | answered | answered | 2/2 | 0/2 | 1/1 | 1/1 | no |
| `scope_and_version_before_ranking` | holdout | `holdout-07-data-platform-authorized` | answered | answered | 1/1 | 2/2 | 1/1 | 1/1 | no |
| `scope_and_version_before_ranking` | holdout | `holdout-08-historical-tag-report` | answered | answered | 1/1 | 1/1 | 1/1 | 1/1 | no |
| `scope_and_version_before_ranking` | holdout | `holdout-09-wrong-scope-job-pause` | abstained | answered | 0/0 | 0/0 | 1/1 | 1/1 | yes |
| `scope_and_version_before_ranking` | holdout | `holdout-10-absent-deletion-approval` | abstained | answered | 0/0 | 0/0 | 1/1 | 1/1 | yes |
| `scope_and_version_before_ranking` | holdout | `holdout-11-anomaly-conflict` | conflict | answered | 2/2 | 0/1 | 1/1 | 1/1 | no |
| `scope_and_version_before_ranking` | holdout | `holdout-12-injected-approval` | answered | answered | 1/1 | 0/1 | 1/1 | 1/1 | no |
