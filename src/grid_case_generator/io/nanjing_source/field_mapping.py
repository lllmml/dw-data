"""Shared source-field conversion policy; never completes missing data."""
from decimal import Decimal
import re

from grid_case_generator.models.quality import QualityIssueCode as Code
from grid_case_generator.models.types import SwitchState
from .mapping import _issue, _optional_decimal, _optional_boolean


class SourceFields:
    def __init__(self, raw, dataset_id, case_id, target_ref):
        self.raw = raw
        self.values = dict(raw.fields or ())
        self.dataset_id = dataset_id
        self.case_id = case_id
        self.target_ref = target_ref
        self.issues = []

    def issue(self, field, path, code, message):
        self.issues.append(_issue(dataset_id=self.dataset_id, case_id=self.case_id,
            record=self.raw, target_ref=self.target_ref, field_path=path, code=code,
            observed_value=self.values.get(field), occurrence_key=field, message=message))

    def text(self, field):
        return self.values.get(field) or None

    def decimal(self, field, path, *, positive=False, nonnegative=False, pf=False):
        value, issue = _optional_decimal(self.values.get(field, ''), dataset_id=self.dataset_id,
            case_id=self.case_id, record=self.raw, target_ref=self.target_ref,
            field_path=path, source_field=field)
        if issue:
            self.issues.append(issue)
        if value is not None and ((positive and value <= 0) or
                (nonnegative and value < 0) or (pf and abs(value) > 1)):
            self.issue(field, path, Code.SOURCE_VALUE_OUT_OF_RANGE, 'source numeric value is outside its contract range')
        return value

    def integer(self, field, path):
        value = self.decimal(field, path, positive=True)
        if value is None:
            return None
        if value != value.to_integral_value():
            self.issue(field, path, Code.SOURCE_VALUE_PARSE_FAILED, 'source value is not an integer')
            return None
        return int(value)

    def boolean(self, field, path):
        value, issue = _optional_boolean(self.values.get(field, ''), dataset_id=self.dataset_id,
            case_id=self.case_id, record=self.raw, target_ref=self.target_ref,
            field_path=path, source_field=field)
        if issue:
            self.issues.append(issue)
        return value

    def state(self, field, path):
        value = self.text(field)
        if value is None:
            return None
        if value in ('Open', 'Closed'):
            return SwitchState(value.upper())
        self.issue(field, path, Code.SOURCE_ENUM_UNKNOWN, 'unknown source switch state')
        return SwitchState.UNKNOWN

    def phase(self, field, path):
        if self.text(field):
            self.issue(field, path, Code.SOURCE_ENUM_UNKNOWN, 'source phase encoding is unconfirmed; original text retained')
        return None

    def identifier(self, field, path, *, reference=False):
        value = self.text(field)
        if value and (re.fullmatch(r'[+-]?\d+(?:\.\d+)?[eE][+-]?\d+', value) or
                      re.fullmatch(r'\d+\.\d+', value)):
            self.issue(field, path, Code.SOURCE_IDENTIFIER_SUSPICIOUS_FORMAT, 'suspicious identifier text retained without repair')
        if reference and value == '0':
            self.issue(field, path, Code.SOURCE_REFERENCE_INVALID_LITERAL, 'source reference literal 0 retained without repair')
