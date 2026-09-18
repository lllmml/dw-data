# Q-CASE-001 review:南京 case boundary / D4.2

Status: **REQUIRES_BUSINESS_CONFIRMATION**. Q-CASE-001 remains **OPEN**.

## Current hypothesis

Operational hypothesis: one source directory = one independent GridCase. This audit does not change that contract, resolve Canonical references globally, merge cases, write topology or approve any proposal.

## Evidence supporting it

The 5,159 directories preserve separate source records and feeder identities. No external candidate shares an exact raw Feeder_ID or exact nonempty Feeder_Name with its referring Case in this intake. 90,848 external field occurrences have cross-station candidates (91.8083%); ownership cannot be inferred from an ID match. Existing boundaries prevent these references from silently joining independent feeder heads.

## Evidence against it

98,954 unresolved nonempty field occurrences have definitions elsewhere in the SAME intake; 97,293 have exactly one external row. They affect 3,220 referring Cases and 3,219 published source Feeders. This is too widespread to dismiss as a few isolated missing IDs. 8,103 references have same-station candidates (8.1887%); 5,273 have a reverse directory direction (5.3287%). These facts challenge the assumption that every unresolved endpoint denotes absent source data.

## Observed export-partition patterns

The complete candidate graph has 36,240 directed directory edges, 1,441 WCC including isolated Cases, 3,675 SCC and a largest WCC of 3,698 Cases. WCC is the undirected connected-component count; it is not a demonstrated electrical component. All-candidate global follow would involve 3,739 current GridCases. Ambiguous matches are included as possibilities, not selected connections.

The stricter unique/same-station/voltage-compatible reciprocal subgraph contains **174 POSSIBLE_EXPORT_PARTITION_CLUSTER** observations. These are separate from the full WCC. They indicate possible station-level export organization or recorded inter-feeder references, not proven common feeder ownership. Exact same-feeder ID/name observations: 0. Similar directory names such as 新锦城#1/#3/4号线 are visible in the witnesses, but remain distinct source Feeder identities. No fuzzy naming was used.

| Candidate cluster | Cases | Station IDs | Example source directories |
|---|---:|---|---|
| `535f8d19b167` | 4 | 113997367245537424 | 数据/北门变_国信#1线; 数据/北门变_香山湖线; 数据/北门变_望景线 |
| `49746cebabfa` | 4 | 113997366104687146 | 数据/雄州变_10kV莉湖#2线; 数据/雄州变_10kV华亚#1线; 数据/雄州变_10kV石林#2线 |
| `ec7b2f02c395` | 4 | 113997367245538025 | 数据/西岗变_10kV新锦城#3线112; 数据/西岗变_10kV新锦城4号线132; 数据/西岗变_10kV新锦城#1线113 |
| `7e9fd03eede5` | 4 | 113997367245537425 | 数据/夹河变_X华城#4线; 数据/夹河变_X华城#3线; 数据/夹河变_X华城#1线 |
| `a1fc1f4ed840` | 3 | 113997367245537302 | 数据/小营变_10kV未来城#2线133; 数据/小营变_10kV未来城#1线124; 数据/小营变_10kV地质线116 |
| `8c696ebc9457` | 3 | 113997367245537307 | 数据/新庄变_10kV常发广场#1线117; 数据/新庄变_10kV常发广场4号线136; 数据/新庄变_10kV常发广场#2线145 |
| `699d6af90ecd` | 3 | 113997367245537423 | 数据/高新变_X南瑞线; 数据/高新变_X材料线; 数据/高新变_X电子线 |
| `17b6bdf2d0dd` | 3 | 113997367245537341 | 数据/沙洲变_10kV庐山路#2线12A; 数据/沙洲变_10kV新安江路#2线129; 数据/沙洲变_10kV新安江路#1线119 |
| `ed068d04e910` | 3 | 113997367245537300 | 数据/云南路变_10kV易华里线271; 数据/云南路变_10kV江苏路线281; 数据/云南路变_10kV宁海路线274 |
| `696fbcff5ed8` | 2 | 113997366104687050 | 数据/中央门变_10kV南汽#2线212; 数据/中央门变_10kV南汽#1线112 |
| `759ed153071d` | 2 | 113997367245538088 | 数据/汤庄变_10kV汤觉线125; 数据/汤庄变_10kV汤明线115 |
| `5b5b2b66f3c9` | 2 | 113997367245537344 | 数据/江东门变_10kV熙岸#4线12H; 数据/江东门变_10kV熙岸#1线118 |

Every member, direction, reciprocal pair, feeder identity, voltage domain, entity-type composition and ownership ambiguity is preserved in `case_reference_components.jsonl`; this table is a sample, not a selection for merge.

## Full-dataset counts

| Measure | Field occurrences / cases |
|---|---:|
| UNIQUE_EXTERNAL_MATCH | 97,293 |
| MULTIPLE_EXTERNAL_MATCH | 1,661 |
| CROSS_TYPE_EXTERNAL_MATCH (overlapping) | 0 |
| UNDEFINED_GLOBAL | 34,750 |
| LOCAL_UNRESOLVED_ONLY | 3,148 |
| Same-station external references / candidate matches | 8,103 / 14,318 |
| Cross-station external references / candidate matches | 90,848 / 114,576 |
| Voltage-context conflict references | 57,927 |
| Conflicts with direct voltage fields on BOTH sides | 0 |
| Global raw identity rows | 950,605 |
| Case-local EXACT references excluded | 432,008 |
| Empty raw reference fields excluded | 890,285 |

A context conflict compares an endpoint with a source-head voltage observation; it must not be advertised as a proven terminal-voltage contradiction. Transformer multi-domain candidates remain UNKNOWN without a unique terminal side. The same/cross-station counts overlap when an ambiguous reference has candidates in both contexts.

External references by owner source file type: BUS=179, LINE=3,525, SWITCH=95,250. Other registered types were scanned even when their endpoint columns were blank or their files had no data rows.

## 78 insufficient Feeder

| Primary classification | Feeders |
|---|---:|
| LIKELY_EXPORT_PARTITION | 11 |
| UNIQUE_EXTERNAL_BUT_OWNERSHIP_UNCONFIRMED | 43 |
| AMBIGUOUS_EXTERNAL_REFERENCE | 0 |
| CROSS_STATION_OR_VOLTAGE_CONFLICT | 24 |
| TRULY_MISSING_GLOBAL_REFERENCE | 0 |

These Feeders have 96 case-local unresolved Line endpoint field occurrences: 96 unique external, 0 multiple, 0 globally undefined; 69 same-station, 38 reciprocal, 96 voltage-compatible. Counts measure references, not accepted placements. The full per-Feeder witnesses and identity/placement bounds are in `target_78_feeders.jsonl`.

The prior D4.1 suggestion that all 78 require a missing sibling-Case export is withdrawn. Their relevant Line target definitions already exist in this intake. Distinguish EXTERNAL_PARTITIONED_DATA (located in another directory) from OWNERSHIP_UNCONFIRMED (not licensed for connection); neither proves that the directory should be merged. AMBIGUOUS_EXTERNAL_DATA and MISSING_DATA remain separate classifications.

## Counterfactual impact

**ANALYSIS_ONLY_CROSS_CASE_COUNTERFACTUAL**

Under unique + same-station + voltage-compatible + type/identity-compatible selection, 2,544 reference identities are safe-looking analytical candidates, including 1,252 Line endpoints. 1,251 source Lines would have both endpoint identities accounted for. This is an identity-completeness upper bound, not a count of representable or reachable Lines.

Existing accepted-anchor calculation: 0 additional Line representations, 0 additional backbone-eligible Feeders, reachable Line delta 0, reachable Transformer delta 0. Physical and conducting calculations both preserve the base graph. Broader placement/reachability impact is **undetermined**, not zero: 1,251 identity-complete Lines lack proven accepted attachment anchors. Counting their placement would require choosing an unapproved interpretation for foreign Switch ports or unrepresented entities. No such topology or proposal was generated.

For the 78 cohort, the strict selection makes 50 Line identities complete, but 0 Lines gain an existing accepted-anchor representation. Per-Feeder broader effects remain unassessed where placement is missing.

## Risks of relaxing it

Cross-feeder ownership and head contamination are explicit risks even for same-station matches. The all-candidate graph spans thousands of directories; blindly joining it can cause massive component merging. Multiple candidates must not be resolved by ordering. Directory reciprocity is not electrical reciprocity. Voltage context conflicts and station mismatches require witnesses and review. Existing-anchor counterfactual diagnostics compute cycles, OPEN-cut bypass and multiple-head merging, but their zero deltas here result from zero representable added Lines and do not certify unrestricted global follow as safe.

## Risks of keeping it

Case-local isolation leaves valid external identity evidence unused and can mislabel existing data as absent. It can also make synthetic completion appear necessary before the source export boundary is understood. Retain operational isolation while publishing the global evidence as a review layer.

## Missing data request

Do not request replacement sibling exports for all 78. Request the export partition/key/ownership semantics and selected witnessed cross-station pairs first. Across the full intake, 34,750 nonempty fields are globally undefined, including 10,318 SimConfig `SUB_10KV` references; these repeated placeholders must not be conflated with 34,750 missing physical assets. Undefined owner-type counts: {'BUS': 115, 'LINE': 1, 'SIM_CONFIG': 10318, 'SWITCH': 24316}.

There is one globally undefined Line endpoint in the full dataset (outside the 78 cohort). Its raw literal is `0`, already an invalid-reference placeholder, so request the intended endpoint declaration rather than claiming a missing physical asset:

- `数据/未知变电站_馈线_3799912185593957528`; `Line_FromBus` = `0`; `zip-member:%E6%95%B0%E6%8D%AE/%E6%9C%AA%E7%9F%A5%E5%8F%98%E7%94%B5%E7%AB%99_%E9%A6%88%E7%BA%BF_3799912185593957528/08_Line.csv#data-row=2`.

Of the 1,259 no-source-Line Feeders, 27 have 48 external field occurrences. This does not supply a layout basis, and no layout generation was attempted. The remainder's lack of external references does not itself approve a synthetic layout policy.

## Recommendation status and next minimum slice

**REQUIRES_BUSINESS_CONFIRMATION**. Q1: a systematic reference pattern, not merely isolated dirty IDs. Q2: station-level partition observations exist; same actual feeder ownership is unproven. Q3: directory = GridCase is an operational restriction, not a verified export semantic. Q4/Q5: identity recovery is quantified above, separately from unique placement. Q6: global following has material ownership/merging risks and remains prohibited.

Next minimum slice: a business review of exact source witnesses for (a) same-station reciprocal clusters, (b) unique cross-station references, and (c) the single undefined Line endpoint. Obtain explicit export-partition and feeder ownership decisions with examples. Keep any later reference-resolution or case-merge implementation behind separate authorization; do not enter D5/E3/OpenDSS/QSTS.

## Reproduction and immutable inputs

Formal artifact: `outputs/nanjing-e2-3/case-boundary-audit-v1/`. Source-bound verifier rebuilds every stream from inventory/row evidence and immutable D3/accepted inputs. Independent hash-seed output: `case-boundary-audit-v1-reproduction`. See the [run guide](../guides/nanjing_case_boundary_audit.md) and the delivery handoff for verification hashes/results.
