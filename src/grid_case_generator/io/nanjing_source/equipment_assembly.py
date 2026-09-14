"""Publish Equipment bundles using existing identity classification results."""
from collections import defaultdict
from dataclasses import replace

from grid_case_generator.models.identifiers import SourceImportIdFactory as IDs
from grid_case_generator.models.types import EntityRef, Identifier, IdentityStatus
from grid_case_generator.models.quality import QualityIssueCode as Code
from grid_case_generator.validation.reference_resolution import ReferenceIdentityConflict
from grid_case_generator.validation.identity import SourceEntityType
from .mapping import _issue


def assemble_equipment(outcomes, *, dataset_id, case_id):
    groups = defaultdict(list)
    published, issues, unmapped, conflicts = [], [], [], []
    refs_by_row = {}
    for raw, outcome in outcomes:
        if outcome.record is not None:
            eq = outcome.record.equipment
            if (eq.source_record_ref != raw.source_record_ref or eq.case_id != case_id
                    or eq.equipment_type.value != raw.source_file_type.value
                    or eq.record_origin.value != 'SOURCE'):
                raise ValueError('Equipment outcome does not match associated raw row')
        if outcome.record is None:
            unmapped.append(outcome.unmapped_record)
            issues.extend(outcome.issues)
            continue
        eq = outcome.record.equipment
        groups[(eq.equipment_type,eq.source_id)].append((raw,outcome))
    for (kind,source_id), group in sorted(groups.items()):
        group.sort(key=lambda item:item[0].source_record_ref)
        representative = group[0][1].record
        status = representative.equipment.identity_status
        if any(outcome.record.equipment.identity_status is not status for _,outcome in group):
            raise ValueError('Equipment identity group has inconsistent statuses')
        identical = all(raw.fields == group[0][0].fields for raw,_ in group)
        if status is IdentityStatus.UNIQUE and len(group) != 1:
            raise ValueError('multiple Equipment rows cannot be UNIQUE')
        if status is IdentityStatus.DUPLICATE_IDENTICAL and (len(group)<2 or not identical):
            raise ValueError('identical Equipment group must contain identical rows')
        if status is IdentityStatus.DUPLICATE_CONFLICT and (len(group)<2 or identical):
            raise ValueError('conflicting Equipment group must contain distinct rows')
        if status is IdentityStatus.DUPLICATE_CONFLICT:
            ref = None
            conflicts.append(ReferenceIdentityConflict(case_id=case_id,
                source_entity_type=SourceEntityType(kind.value),source_id=source_id,
                source_record_refs=tuple(raw.source_record_ref for raw,_ in group)))
        else:
            published.append(representative)
            ref = EntityRef(entity_type=Identifier('EQUIPMENT'),entity_id=representative.equipment.equipment_id)
        for raw,outcome in group:
            refs_by_row[raw.source_record_ref] = ref
            for issue in outcome.issues:
                # Mapping field issues target Equipment; source field is the frozen occurrence key.
                old_ref = issue.target_ref
                if old_ref == ref:
                    issues.append(issue)
                    continue
                source_field = next((name for name,_ in raw.fields
                    if IDs.quality_issue_id(dataset_id,case_id,old_ref,issue.field_path,issue.code,
                        raw.source_record_ref,name) == issue.issue_id), None)
                if source_field is None:
                    raise ValueError('unrecognized mapper issue identity')
                issues.append(replace(issue,target_ref=ref,issue_id=IDs.quality_issue_id(
                    dataset_id,case_id,ref,issue.field_path,issue.code,raw.source_record_ref,source_field)))
            if status is not IdentityStatus.UNIQUE:
                code = Code.SOURCE_ID_DUPLICATE_IDENTICAL if status is IdentityStatus.DUPLICATE_IDENTICAL else Code.SOURCE_ID_DUPLICATE_CONFLICT
                issues.append(_issue(dataset_id=dataset_id,case_id=case_id,record=raw,target_ref=ref,
                    field_path='equipment.source_id',code=code,observed_value=source_id,
                    occurrence_key='',message='source Equipment identity has duplicate rows'))
    return tuple(published),tuple(issues),tuple(unmapped),tuple(conflicts),refs_by_row
