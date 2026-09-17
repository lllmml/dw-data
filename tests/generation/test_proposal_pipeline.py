def test_six_bound_inputs_reproduction_and_immutability(tmp_path):
    import csv
    import io
    from decimal import Decimal
    from zipfile import ZipFile
    from source_fixture import SCHEMA
    from test_switch_semantics import fixture
    from grid_case_generator.io.nanjing_source.import_pipeline import import_archive
    from grid_case_generator.io.topology_artifacts import audit_source_artifact
    from grid_case_generator.io.switch_projection_artifacts import run_projection_analysis
    from grid_case_generator.analysis.switch_projection_proposal import render_proposal
    from grid_case_generator.io.feeder_coverage_artifacts import run_feeder_analysis
    from grid_case_generator.analysis.feeder_coverage_cli import render_report
    from grid_case_generator.io.topology_recovery_artifacts import run_recovery_analysis
    from grid_case_generator.io.completion_artifacts import run_completion_analysis, verify_completion_inputs
    from grid_case_generator.models.topology import TopologyConfig
    archive=tmp_path/'fixture.zip'; rows=fixture()
    rows['TRANSFORMER'].append({'Transformer_ID':'orphan'})
    with ZipFile(archive,'w') as z:
        for case,data in [('ordinary',rows),('empty',{})]:
            for schema in SCHEMA.files:
                stream=io.StringIO(newline='');writer=csv.writer(stream);writer.writerow(schema.header)
                for row in data.get(schema.file_type.value,[]):writer.writerow([row.get(k,'') for k in schema.header])
                z.writestr(case+'/'+schema.filename,stream.getvalue())
    roots={k:tmp_path/k for k in ('source','baseline','projection','feeder','recovery')}
    import_archive(archive,roots['source'],imported_at='2026-09-17T00:00:00Z')
    audit_source_artifact(roots['source'],roots['baseline'],TopologyConfig(Decimal('10.5')))
    run_projection_analysis(roots['source'],roots['baseline'],roots['projection'],render_proposal)
    run_feeder_analysis(roots['source'],roots['baseline'],roots['projection'],roots['feeder'],render_report)
    run_recovery_analysis(roots['source'],roots['baseline'],roots['projection'],roots['feeder'],roots['recovery'])
    snapshot=lambda root:{str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    run_completion_analysis(roots,tmp_path/'d1')
    roots['d1']=tmp_path/'d1'
    from grid_case_generator.io.proposal_artifacts import run_proposal_analysis, verify_proposal_artifact, verify_proposal_inputs
    from grid_case_generator.models.proposals import DECISION_SCHEMA, decision_bytes
    checks=verify_proposal_inputs(roots)
    policy={'schema_version':DECISION_SCHEMA,'decision_version':'1.0.0',
        'input_manifest_sha256':{k:checks[k] for k in ('source','d1')},'decisions':[]}
    decision=tmp_path/'decisions.json';decision.write_bytes(decision_bytes(policy))
    before={k:snapshot(p) for k,p in roots.items()};raw_before=archive.read_bytes()
    for name in ('proposal','reproduction'):
        result=run_proposal_analysis(roots,decision,tmp_path/name)
        assert result['case_count']==2 and result['feeder_count']==1
        verify_proposal_artifact(tmp_path/name,roots)
    assert snapshot(tmp_path/'proposal')==snapshot(tmp_path/'reproduction')
    assert before=={k:snapshot(p) for k,p in roots.items()}
    assert raw_before==archive.read_bytes()
