"""Synthetic completion-export source archive fixture for delivery tests.

Builds a three-Case ZIP whose members all begin with the UTF-8 BOM and use CRLF,
except three members in the third Case that carry deliberate byte-format edges a
re-serializing writer would erase: LF-only line endings, a missing trailing
terminator, and a quoted field holding a comma plus an embedded newline. Every
byte here is synthetic; the real intake is never read.
"""
import csv
import io
from pathlib import Path
from zipfile import ZipFile

from grid_case_generator.io.nanjing_source.schema import NANJING_SOURCE_SCHEMA as SCHEMA
from grid_case_generator.models.completion_export import CompletionPolicy
from grid_case_generator.models.identifiers import SourceImportIdFactory as IDs

BOM = b'\xef\xbb\xbf'
# The seed below is chosen so the three hash-derived case_ids do NOT come out in
# source_case_key order ('a'*64 happens to sort them), which would let a writer
# keying its ordering assertion on case_id pass by accident.
DATASET = IDs.dataset_id('b' * 64)

# source_case_keys are ordered by Unicode code point (丙 < 乙 < 甲) so the
# provenance rows emitted in case order are already sorted, as the writer's
# ordering test requires.
_POPULATED_ROWS = {
    'STATION': [
        {'Station_ID': 'S-JIA', 'Station_Type': 'distribution', 'Station_Name': '甲变',
         'Station_Voltage_Level': '10kV', 'Station_Lon': '118.1000', 'Station_Lat': '32.1000'},
    ],
    'BUS': [
        {'Bus_ID': 'B-JIA-1', 'Bus_Name': '甲母线一', 'Bus_BaseKV': '10.5', 'Bus_Phase': 'ABC',
         'Bus_Station_ID': 'S-JIA', 'Bus_IsSource': 'true'},
        {'Bus_ID': 'B-JIA-2', 'Bus_Name': '甲母线二', 'Bus_BaseKV': '10.5', 'Bus_Phase': 'ABC',
         'Bus_Station_ID': 'S-JIA', 'Bus_IsSource': 'false'},
    ],
    'FEEDER': [
        {'Feeder_ID': 'F-JIA', 'Feeder_Name': '甲线101', 'Feeder_SourceBus': 'B-JIA-1'},
    ],
    'LINE': [
        {'Line_ID': 'L-JIA-1', 'Line_FromBus': 'B-JIA-1', 'Line_ToBus': 'B-JIA-2', 'Line_Phase': 'ABC',
         'Line_Type': 'cable', 'Line_Model': 'YJV22', 'Line_Length_km': '1.2',
         'Line_R1_ohm_per_km': '0.1', 'Line_X1_ohm_per_km': '0.2', 'Line_NumCircuits': '1'},
        {'Line_ID': 'L-JIA-2', 'Line_FromBus': 'B-JIA-2', 'Line_ToBus': 'B-JIA-3', 'Line_Phase': 'ABC',
         'Line_Type': 'cable', 'Line_Model': 'YJV22', 'Line_Length_km': '0.8',
         'Line_R1_ohm_per_km': '0.1', 'Line_X1_ohm_per_km': '0.2', 'Line_NumCircuits': '1'},
    ],
    'LOAD': [
        {'Load_ID': 'LD-JIA-1', 'Load_Bus': 'B-JIA-2', 'Load_Phase': 'ABC', 'Load_P_kW': '500',
         'Load_Q_kVAR': '120', 'Load_PF': '0.97'},
        {'Load_ID': 'LD-JIA-2', 'Load_Bus': 'B-JIA-3', 'Load_Phase': 'ABC', 'Load_P_kW': '300',
         'Load_Q_kVAR': '80', 'Load_PF': '0.96'},
    ],
    'TRANSFORMER': [
        {'Transformer_ID': 'T-JIA-1', 'Transformer_FromBus': 'B-JIA-1', 'Transformer_ToBus': 'B-JIA-4',
         'Transformer_Phase': 'ABC', 'Transformer_RatedCapacity_kVA': '1000',
         'Transformer_HighVoltage_kV': '10.5', 'Transformer_LowVoltage_kV': '0.4',
         'Transformer_R_pct': '1.0', 'Transformer_X_pct': '4.0', 'Transformer_ConnHV': 'Dyn11',
         'Transformer_ConnLV': 'Dyn11', 'Transformer_NumTaps': '5', 'Transformer_TapRange': '0.05'},
    ],
}

_EDGE_ROWS = {
    'DISCONNECTOR': [
        {'Disconnector_ID': 'D-BING-1', 'Disconnector_FromBus': 'B-BING-1',
         'Disconnector_ToBus': 'B-BING-2', 'Disconnector_NormalState': 'open'},
    ],
    'EARTHING_SWITCH': [
        {'EarthingSwitch_ID': 'E-BING-1', 'EarthingSwitch_Bus': 'B-BING-1',
         'EarthingSwitch_State': 'open'},
    ],
    'ACCESS_POINT': [
        {'AccessPoint_ID': 'AP-BING-1', 'AccessPoint_Bus': 'B-BING-1', 'AccessPoint_Phase': 'ABC',
         'AccessPoint_UserType': 'residential,high\nrise', 'AccessPoint_ContractCapacity_kVA': '100'},
    ],
}


def _ordinary_bytes(schema, rows):
    """Ordinary member: BOM + header and rows via csv.writer (CRLF, trailing terminator)."""
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(schema.header)
    for row in rows:
        writer.writerow([row.get(k, '') for k in schema.header])
    return BOM + stream.getvalue().encode('utf-8')


def _lf_bytes(schema, rows):
    """LF-only line endings; a re-serializing writer would emit CRLF instead."""
    lines = [','.join(schema.header)]
    for row in rows:
        lines.append(','.join(str(row.get(k, '')) for k in schema.header))
    return BOM + ('\n'.join(lines) + '\n').encode('utf-8')


def _no_trailing_bytes(schema, rows):
    """CRLF between records but no final terminator on the last record."""
    lines = [','.join(schema.header)]
    for row in rows:
        lines.append(','.join(str(row.get(k, '')) for k in schema.header))
    return BOM + '\r\n'.join(lines).encode('utf-8')


def _quoted_bytes(schema, rows):
    """CRLF with a quoted field holding a comma and an embedded newline."""
    lines = [','.join(schema.header)]
    for row in rows:
        values = []
        for k in schema.header:
            value = str(row.get(k, ''))
            if ',' in value or '\n' in value or '"' in value:
                value = '"' + value.replace('"', '""') + '"'
            values.append(value)
        lines.append(','.join(values))
    return BOM + '\r\n'.join(lines).encode('utf-8')


class DeliveryFixture:
    def __init__(self, tmp_path, archive, roots, members, cases, source_row_count,
                 feederless_key, lf_member, no_trailing_member, quoted_member, policy):
        self.tmp_path = tmp_path
        self.archive = archive
        self.roots = roots
        self.members = members
        self.cases = cases
        self.source_row_count = source_row_count
        self.feederless_key = feederless_key
        self.lf_member = lf_member
        self.no_trailing_member = no_trailing_member
        self.quoted_member = quoted_member
        self.policy = policy

    def write_args(self):
        return {
            'cases': self.cases,
            'archive_path': self.archive,
            'policy': self.policy,
            'roots': self.roots,
        }

    def write(self, **overrides):
        kwargs = self.write_args()
        kwargs.update(overrides)
        root = self.tmp_path / 'delivery'
        from grid_case_generator.io.derived_delivery_artifacts import write_delivery
        write_delivery(root, **kwargs)
        return root


def build(tmp_path):
    tmp_path = Path(tmp_path)
    archive = tmp_path / 'source.zip'
    source_root = tmp_path / 'source-root'
    source_root.mkdir(parents=True, exist_ok=True)
    roots = {'source': source_root}

    policy = CompletionPolicy(
        policy_version='1.0.0',
        materialize_tiers=('SAME_STATION', 'CROSS_STATION'),
        enabled_rules=('CROSS_CASE_REFERENCE_COPY_V1',),
        max_reference_closure_depth=4,
        placement_endpoint_bus=False,
    )

    cases_spec = (
        {
            'source_case_key': '数据/丙变_10kV丙线303',
            'rows': _EDGE_ROWS,
            'lf': '04_Disconnector.csv',
            'no_trailing': '06_EarthingSwitch.csv',
            'quoted': '07_AccessPoint.csv',
        },
        {
            'source_case_key': '数据/乙变_10kV乙线202',
            'rows': {},
        },
        {
            'source_case_key': '数据/甲变_10kV甲线101',
            'rows': _POPULATED_ROWS,
        },
    )

    members = []
    cases = []
    source_row_count = 0
    special = {}

    with ZipFile(archive, 'w') as z:
        for spec in cases_spec:
            key = spec['source_case_key']
            per_case = []
            for schema in SCHEMA.files:
                member = f"{key}/{schema.filename}"
                rows = spec['rows'].get(schema.file_type.value, [])
                if schema.filename == spec.get('lf'):
                    data = _lf_bytes(schema, rows)
                elif schema.filename == spec.get('no_trailing'):
                    data = _no_trailing_bytes(schema, rows)
                elif schema.filename == spec.get('quoted'):
                    data = _quoted_bytes(schema, rows)
                else:
                    data = _ordinary_bytes(schema, rows)
                z.writestr(member, data)
                members.append((key, member))
                per_case.append((schema.file_type, member))
                source_row_count += len(rows)
                if schema.filename == spec.get('lf'):
                    special['lf'] = member
                elif schema.filename == spec.get('no_trailing'):
                    special['no_trailing'] = member
                elif schema.filename == spec.get('quoted'):
                    special['quoted'] = member
            cases.append((IDs.case_id(DATASET, key), key, tuple(per_case)))

    return DeliveryFixture(
        tmp_path=tmp_path,
        archive=archive,
        roots=roots,
        members=tuple(members),
        cases=tuple(cases),
        source_row_count=source_row_count,
        feederless_key='数据/乙变_10kV乙线202',
        lf_member=special['lf'],
        no_trailing_member=special['no_trailing'],
        quoted_member=special['quoted'],
        policy=policy,
    )
