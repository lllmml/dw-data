import json
import pytest
from grid_case_generator.validation.placement_provenance import compare_versions


def test_only_provenance_and_version_changes_are_permitted(tmp_path):
    old = tmp_path / 'old'; new = tmp_path / 'new'
    old.mkdir(); new.mkdir()
    for root, evidence, version in ((old, 'RULE_INFERRED', '1.0.0'),
                                     (new, 'UNRESOLVED', '1.1.0')):
        (root / 'detail.jsonl').write_text(json.dumps({'node_id': 'stable',
            'evidence_class': evidence, 'rule_version': version}) + '\n')
        (root / 'counterfactual_coverage.json').write_text('{"nodes":2}\n')
    assert compare_versions(old, new)['topology_coverage_replay_unchanged']
    (new / 'detail.jsonl').write_text('{"node_id":"changed"}\n')
    with pytest.raises(ValueError, match='structural'):
        compare_versions(old, new)
