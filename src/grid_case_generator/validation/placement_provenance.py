"""Read-only comparison of historical and corrected D4.1 calculations."""
import json
from pathlib import Path


def _without_metadata(value):
    if isinstance(value, dict):
        return {k: _without_metadata(v) for k, v in value.items()
                if k not in ('evidence_class', 'rule_version', 'version')}
    if isinstance(value, list):
        return [_without_metadata(v) for v in value]
    return value


def compare_versions(historical, corrected):
    """Require unchanged identities, graph, classifications, coverage and replay."""
    historical, corrected = Path(historical), Path(corrected)
    names = {p.name for p in historical.iterdir()}
    if names != {p.name for p in corrected.iterdir()}:
        raise ValueError('D4.1 comparison inventory mismatch')
    checked = []
    for name in sorted(names - {'manifest.json', 'report.md'}):
        before = [json.loads(line) for line in (historical / name).read_bytes().splitlines()]
        after = [json.loads(line) for line in (corrected / name).read_bytes().splitlines()]
        if _without_metadata(before) != _without_metadata(after):
            raise ValueError('D4.1 structural calculation changed: ' + name)
        checked.append(name)
    if (historical / 'counterfactual_coverage.json').read_bytes() != \
            (corrected / 'counterfactual_coverage.json').read_bytes():
        raise ValueError('D4.1 coverage bytes changed')
    return {'topology_coverage_replay_unchanged': True, 'checked_streams': checked,
            'allowed_changes': ['evidence_class', 'rule_version', 'version',
                                'manifest', 'report rendering']}
