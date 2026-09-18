# E2.3 D4.1 provenance fix + D4.2 case boundary audit handoff

Baseline: `7895f0d917a26d5ca300d307106d5c6d296c7ba3`; initial worktree clean except the
known untracked `CLAUDE.md`, which was not changed. No new dependency.

## Part A: provenance contract correction

The historical placement-evidence-v1 incorrectly labelled unapproved placement objects
RULE_INFERRED, contrary to the frozen recovery taxonomy. That taxonomy is unchanged.
The historical artifact is preserved byte-for-byte. New artifact
`outputs/nanjing-e2-3/placement-evidence-v1-1/` supersedes the historical provenance
interpretation. Artifact/schema and rule-analysis version: **1.1.0**.

- Placement anchors: **565 UNRESOLVED**, **0 RULE_INFERRED**.
- Line representations: **684 UNRESOLVED**, **0 RULE_INFERRED**.
- All four placement rules remain unapproved, with approved=false/applied=false.
- Generated semantic identities keep the 1.0.0 namespace so node/edge IDs stay stable.
- Every detail stream compares equal after removing only evidence_class/version metadata.
- Topology counts, coverage, decisions and D4 replay are unchanged; counterfactual coverage
  is byte-identical to v1.
- Current verification rejects historical v1 as stale provenance. Its historical
  reproducibility was checked with the unchanged baseline implementation.
- A rehashed manifest cannot make approved=false + RULE_INFERRED pass verification.

New D4.1 manifest SHA256: `1d41b8d970f464af66376526cdc06da8e57d8c03834f0dbf07251f7bb2c12f2e`.
Independent PYTHONHASHSEED=1/999 reproduction: all **17** files identical.

## Part B: analysis-only source boundary audit

Formal artifact: `outputs/nanjing-e2-3/case-boundary-audit-v1/`.
Independent reproduction: `outputs/nanjing-e2-3/case-boundary-audit-v1-reproduction/`.
Manifest SHA256: `d8c1b78017e328e73444fd57f823892d4985e0fcef6b596147a86d2286562144`.
All **12** files identical across PYTHONHASHSEED=1/999. A third source-bound verifier run
uses seed 37, validates input inventories/checksums, rebuilds all streams and compares
all bytes. Verification receipts are under `outputs/nanjing-e2-3/d4-2-verification/`.

| Measure | Result |
|---|---:|
| Source Cases / indexed raw identities | 5,159 / 950,605 |
| Cross-case reference occurrences | 98,954 |
| Referring Cases / Feeders | 3,220 / 3,219 |
| Unique external / multiple external | 97,293 / 1,661 |
| Cross-type external | 0 |
| Globally undefined / local unresolved only | 34,750 / 3,148 |
| Same-station / cross-station references | 8,103 / 90,848 |
| Same-station / cross-station candidate matches | 14,318 / 114,576 |
| Reciprocal references | 5,273 (5.3287%) |
| WCC / SCC | 1,441 / 3,675 |
| Largest WCC | 3,698 Cases |
| POSSIBLE_EXPORT_PARTITION_CLUSTER | 174 |
| Current GridCases involved by any candidate | 3,739 |
| Voltage-context conflicts / direct-field conflicts | 57,927 / 0 |

Counts above are raw field occurrences unless explicitly labelled candidate matches or
Cases. Context flags overlap. 10,318 of the globally undefined values are the SimConfig
literal SUB_10KV. The only globally undefined Line endpoint is the invalid literal `0`;
this is not evidence of a missing physical device.

The 78 insufficient Feeder split into **11 LIKELY_EXPORT_PARTITION**, **43
UNIQUE_EXTERNAL_BUT_OWNERSHIP_UNCONFIRMED**, **0 AMBIGUOUS_EXTERNAL_REFERENCE**, **24
CROSS_STATION_OR_VOLTAGE_CONFLICT**, **0 TRULY_MISSING_GLOBAL_REFERENCE**. Their 96
unresolved Line endpoints all have unique external definitions; 69 are same-station,
38 reciprocal and 96 voltage-compatible. The previous blanket recommendation to request
missing sibling-Case exports for these 78 is superseded by this evidence.

## Counterfactual limits

Every number is **ANALYSIS_ONLY_CROSS_CASE_COUNTERFACTUAL**. Strict unique + same-station
+ voltage-compatible selection also requires compatible type, unique identity and no
known hard blocker. It yields **2,544** reference-identity candidates, including **1,252
Line endpoints** and an identity-completeness upper bound of **1,251 Lines**.

Existing accepted-anchor calculations yield **0** additional represented Lines, **0**
additional backbone-eligible Feeders, reachable Line delta **0**, reachable Transformer
delta **0**, with physical and conducting metrics reported independently. Broader
placement/backbone/reachability effects remain **null / undetermined**, not zero:
foreign multi-port or unrepresented entities have no confirmed attachment policy.
The 78 cohort has 50 identity-complete Line candidates but no accepted-anchor placement.
No hypothetical Switch port or junction was invented to make these counts positive.

The 1,259 no-source-Line cohort was only counted: 27 Feeders have 48 external references.
No layout was generated. No topology/proposal, Transformer, LV Bus, Load, DER, time series,
E3/OpenDSS/QSTS output was created by the audit.

## Review and next gate

[Q-CASE-001 review](../reviews/2026-09-18-nanjing-case-boundary-review.md) recommends
**REQUIRES_BUSINESS_CONFIRMATION**. Q-CASE-001 remains OPEN. Operational directory =
GridCase, Canonical references and case-local resolution stay unchanged.

The evidence supports a systematic cross-directory reference pattern and some possible
station-level partitions, but the 91.8% cross-station candidate-reference share and
absence of exact shared Feeder IDs/names prevent a blanket "same feeder export shards"
conclusion. First request export-partition and ownership semantics with the review's
source witnesses; request targeted clarification for undefined/placeholder fields.
The next minimum slice is business review of those witnesses, not merge/apply or D5.

## Validation

- Full suite: **554 passed**; meaningful fixtures cover external ambiguity, type/context,
  reciprocal direction, explicit/context voltage distinction, strict clusters, cycles,
  OPEN-cut bypass, source/manifest tamper, deterministic ordering and hash-seed independence.
- `python -m compileall -q src tests` and `git diff --check`: passed.
- Baseline D3 chain, historical D4 and historical D4.1: source-bound verification passed.
- Historical D4 and D4.1 outputs equal their reproduction artifacts.
- Corrected D4.1: source-bound semantic replay passed; all streams structurally unchanged.
- D4.2: full source-bound rebuild verification **passed** (seed 37); receipt:
  `d4-2-verification/audit-source-bound-verification.log`.
- **199,579 protected files unchanged** by SHA256 comparison, covering raw source,
  Canonical source, frozen v1, accepted v2 and historical D1/D2/D3/D4/D4.1 inputs.
- Resolver/mapper implementation unchanged. Known unrelated CLAUDE.md untouched.

No APPROVE, APPLY or cross-case topology connection. STOP after delivery.
