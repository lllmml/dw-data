"""Synthetic completion-export source archive fixture for delivery tests.

Builds a three-Case ZIP whose members all begin with the UTF-8 BOM and use CRLF,
except three members in the third Case that carry deliberate byte-format edges a
re-serializing writer would erase: LF-only line endings, a missing trailing
terminator, and a quoted field holding a comma plus an embedded newline. Every
byte here is synthetic; the real intake is never read.
"""
import csv
import io
from dataclasses import replace
from pathlib import Path
from zipfile import ZipFile

from grid_case_generator.generation.completion_ledger import (
    PLACEMENT_BUS_COLUMNS, CompletionInputs, build_ledger, render_bus_row)
from grid_case_generator.io.nanjing_source.locator import source_record_ref
from grid_case_generator.io.nanjing_source.schema import NANJING_SOURCE_SCHEMA as SCHEMA
from grid_case_generator.models.completion_export import (
    CROSS_CASE_RULE, PLACEMENT_BUS_RULE, CompletionPolicy)
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
    # One Bus row, so the Case has exactly one distinct non-empty Bus_Station_ID and
    # the placement rule's station join has positive evidence to copy.
    'BUS': [
        {'Bus_ID': 'B-BING-0', 'Bus_Name': '丙母线零', 'Bus_BaseKV': '10.5', 'Bus_Phase': 'ABC',
         'Bus_Station_ID': 'S-BING', 'Bus_IsSource': 'true'},
    ],
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

# A fourth Case acting as the cross-case donor: its 03_Switch.csv row 1 is copied
# verbatim into the referring Case's own 03_Switch.csv. The donor also carries a
# populated 02_Bus.csv so it looks like a real donor, though the append path only
# reads the Switch member.
_DONOR_ROWS = {
    'SWITCH': [
        {'Switch_ID': 'SW-DING-1', 'Switch_FromBus': 'B-DING-1', 'Switch_ToBus': 'B-DING-2',
         'Switch_Phase': 'ABC', 'Switch_NormalState': 'closed', 'Switch_IsTie': 'false',
         'Switch_RatedCurrent_A': '630'},
    ],
    'BUS': [
        {'Bus_ID': 'B-DING-1', 'Bus_Name': '丁母线一', 'Bus_BaseKV': '10.5', 'Bus_Phase': 'ABC',
         'Bus_Station_ID': 'S-DING', 'Bus_IsSource': 'true'},
    ],
}


def _schema(filename):
    return next(s for s in SCHEMA.files if s.filename == filename)


def bus_member_bytes(stations=()):
    """A synthetic ``02_Bus.csv``: BOM, header, one row per station value given."""
    schema = _schema('02_Bus.csv')
    rows = [{'Bus_ID': f'B-STATION-{n}', 'Bus_Name': '', 'Bus_BaseKV': '10.5',
             'Bus_Phase': 'ABC', 'Bus_Station_ID': station, 'Bus_IsSource': 'false'}
            for n, station in enumerate(stations, 1)]
    return _ordinary_bytes(schema, rows)


def _ordinary_bytes(schema, rows):
    """Ordinary member: BOM + header and rows via csv.writer (CRLF, trailing terminator)."""
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(schema.header)
    for row in rows:
        writer.writerow([row.get(k, '') for k in schema.header])
    return BOM + stream.getvalue().encode('utf-8')


def _lines(schema, rows, *, quote=False):
    """Header plus one comma-joined string per row; `quote` applies minimal CSV quoting."""
    lines = [','.join(schema.header)]
    for row in rows:
        values = []
        for key in schema.header:
            value = str(row.get(key, ''))
            if quote and (',' in value or '\n' in value or '"' in value):
                value = '"' + value.replace('"', '""') + '"'
            values.append(value)
        lines.append(','.join(values))
    return lines


def _lf_bytes(schema, rows):
    """LF-only line endings; a re-serializing writer would emit CRLF instead."""
    return BOM + ('\n'.join(_lines(schema, rows)) + '\n').encode('utf-8')


def _no_trailing_bytes(schema, rows):
    """CRLF between records but no final terminator on the last record."""
    return BOM + '\r\n'.join(_lines(schema, rows)).encode('utf-8')


def _quoted_bytes(schema, rows):
    """CRLF with a quoted field holding a comma and an embedded newline."""
    return BOM + '\r\n'.join(_lines(schema, rows, quote=True)).encode('utf-8')


PLACEMENT_CASE_KEY = '数据/丙变_10kV丙线303'
PLACEMENT_CASE_ID = IDs.case_id(DATASET, PLACEMENT_CASE_KEY)


class PlacementFixture:
    """A ``Ledger`` over synthetic D4.1 proposals, plus the accessors the tests need.

    ``ports`` are ``(proposal, endpoint side)`` pairs, because a proposal declares
    exactly two endpoint sides. Every one of them is non-``ACCEPTED_NODE``, so every
    one of them is unresolved and needs the Bus row its source declaration names.
    """

    def __init__(self, ledger, inputs, raw_endpoint_value, case_id, case_key):
        self.ledger = ledger
        self.inputs = inputs
        self.raw_endpoint_value = raw_endpoint_value
        self.case_id = case_id
        self.case_key = case_key

    @property
    def policy(self):
        return self.inputs.policy

    def inputs_with(self, **overrides):
        """These inputs with fields replaced, for a test that perturbs exactly one."""
        return replace(self.inputs, **overrides)

    def fields(self, record, ledger=None):
        """The generated Bus row's ledger values, nulls included."""
        for entry in (ledger or self.ledger).bus_plan:
            if record['record_id'] in entry['record_ids']:
                return entry['values']
        raise AssertionError('no bus plan entry cites this record')

    def rendered(self, record, ledger=None):
        """The generated Bus row as the CSV re-parses it: nulls are empty fields."""
        text = render_bus_row(self.fields(record, ledger)).decode('utf-8')
        return dict(zip(PLACEMENT_BUS_COLUMNS,
                        next(csv.reader(io.StringIO(text, newline='')))))

    def assumptions(self, record, ledger=None):
        """Every reason the row's own group recorded for a field it left null."""
        return sorted({r['reason'] for r in (ledger or self.ledger).unresolved_records
                       if r['rule_id'] == PLACEMENT_BUS_RULE
                       and r['case_id'] == record['case_id']
                       and r['raw_reference_value'] == record['raw_reference_value']})


def build_placement(*, ports=None, shared_raw_value=True, voltage='10.5', stations=('1139',),
                    join_mismatch=False, case_key=PLACEMENT_CASE_KEY, rule_enabled=True,
                    lever=True):
    """Build a placement ledger. ``voltage`` is per port: a scalar, ``None``, or a list."""
    if ports is None:
        ports = len(voltage) if isinstance(voltage, list) else 1
    values = ['B-GEN-1'] if shared_raw_value else [f'B-GEN-{n}' for n in range(1, ports + 1)]
    assignments = [(n // 2, n % 2 + 1, values[0] if shared_raw_value else values[n])
                   for n in range(ports)]
    case_id = IDs.case_id(DATASET, case_key)

    def line_ref(proposal_index):
        return str(source_record_ref(f'{case_key}/08_Line.csv', data_row=proposal_index + 1))

    proposals = []
    evidence = []
    for proposal_index in sorted({a[0] for a in assignments}):
        endpoints = [{'side': side, 'anchor_id': f'port-{proposal_index}-{side}',
                      'anchor_origin': 'LINE_PLACEMENT_PROPOSAL_V1',
                      'raw_endpoint_value': value}
                     for index, side, value in assignments if index == proposal_index]
        proposals.append({
            'proposal_id': f'line-proposal-{proposal_index}', 'case_id': case_id,
            'feeder_id': 'feeder-generic', 'source_line_id': f'L-GEN-{proposal_index}',
            'source_line_record_ref': line_ref(proposal_index), 'endpoints': endpoints})
    for index, (proposal_index, side, value) in enumerate(assignments):
        if join_mismatch:
            recorded = f'B-OTHER-{proposal_index}'
        else:
            recorded = value
        evidence.append({
            'case_id': case_id, 'source_line_id': f'L-GEN-{proposal_index}',
            'endpoint_side': side, 'raw_endpoint_value': recorded,
            'voltage_evidence': voltage[index] if isinstance(voltage, list) else voltage})

    policy = CompletionPolicy(
        policy_version='1.1.0', materialize_tiers=('SAME_STATION',),
        enabled_rules=(PLACEMENT_BUS_RULE,) if rule_enabled else (CROSS_CASE_RULE,),
        max_reference_closure_depth=2, placement_endpoint_bus=lever)
    inputs = CompletionInputs(
        policy=policy, source_case_key_by_case={case_id: case_key}, audit_rows=(),
        accepted_additions=(), placement_proposals=tuple(proposals),
        endpoint_evidence=tuple(evidence), placement_feeders=(), backbone_taxonomy=(),
        audit_classification=(), audit_cases=(),
        bus_member_bytes_by_case={case_id: bus_member_bytes(stations)})
    return PlacementFixture(build_ledger(inputs), inputs, values[0], case_id, case_key)


class DeliveryFixture:
    def __init__(self, tmp_path, archive, roots, members, cases, source_row_count,
                 feederless_key, referring_key, donor_key, lf_member, no_trailing_member,
                 quoted_member, policy):
        self.tmp_path = tmp_path
        self.archive = archive
        self.roots = roots
        self.members = members
        self.cases = cases
        self.source_row_count = source_row_count
        self.feederless_key = feederless_key
        self.referring_key = referring_key
        self.donor_key = donor_key
        self.lf_member = lf_member
        self.no_trailing_member = no_trailing_member
        self.quoted_member = quoted_member
        self.policy = policy
        self.append_plan = ()
        self.bus_plan = ()
        self.raw_endpoint_value = None

    def donor_member(self, filename):
        return f'{self.donor_key}/{filename}'

    @property
    def bus_member(self):
        return f'{self.referring_key}/02_Bus.csv'

    @property
    def bus_member_bytes(self):
        with ZipFile(self.archive) as archive:
            return archive.read(self.bus_member)

    @property
    def bus_header(self):
        return next(csv.reader(io.StringIO(self.bus_member_bytes.decode('utf-8-sig'),
                                           newline='')))

    @property
    def bus_stations(self):
        """The referring Case's own Bus_Station_ID values, as the rule would read them."""
        header = self.bus_header
        rows = list(csv.reader(io.StringIO(self.bus_member_bytes.decode('utf-8-sig'),
                                           newline='')))
        index = header.index('Bus_Station_ID')
        return tuple(row[index] for row in rows[1:] if len(row) > index and row[index])

    def placement_bus(self, **kwargs):
        """Attach a placement bus plan for the referring Case to the next write.

        The station evidence is read back out of the delivered member rather than
        passed in, so the fixture exercises the same join the pipeline performs.
        """
        kwargs.setdefault('stations', self.bus_stations)
        placement = build_placement(case_key=self.referring_key, **kwargs)
        self.bus_plan = placement.ledger.bus_plan
        self.raw_endpoint_value = placement.raw_endpoint_value
        return self

    def reparsed_last_bus_row(self):
        root = self.tmp_path / 'delivery'
        data = (root / 'data' / self.bus_member).read_bytes()
        rows = list(csv.reader(io.StringIO(data.decode('utf-8-sig'), newline='')))
        return dict(zip(rows[0], rows[-1]))

    def append_donor_row(self, destination='03_Switch.csv', donor_file='03_Switch.csv',
                         tier='SAME_STATION'):
        donor_ref = source_record_ref(self.donor_member(donor_file), data_row=1)
        referring_ref = source_record_ref(f'{self.referring_key}/{destination}', data_row=1)
        self.append_plan = (
            {
                'destination_member': f'{self.referring_key}/{destination}',
                'donor_source_record_ref': str(donor_ref),
                'source_record_ref': str(referring_ref),
                'tier': tier,
                'record_ids': ('v1-completion:ledger:testrecord',),
            },
        )
        return self

    def write_args(self):
        return {
            'cases': self.cases,
            'archive_path': self.archive,
            'policy': self.policy,
            'roots': self.roots,
            'append_plan': self.append_plan,
            'bus_plan': self.bus_plan,
        }

    def write(self, **overrides):
        kwargs = self.write_args()
        kwargs.update(overrides)
        root = self.tmp_path / 'delivery'
        from grid_case_generator.io.derived_delivery_artifacts import write_delivery
        self.result = write_delivery(root, **kwargs)
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
            'source_case_key': '数据/丁变_10kV丁线404',
            'rows': _DONOR_ROWS,
        },
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
        referring_key='数据/丙变_10kV丙线303',
        donor_key='数据/丁变_10kV丁线404',
        lf_member=special['lf'],
        no_trailing_member=special['no_trailing'],
        quoted_member=special['quoted'],
        policy=policy,
    )
