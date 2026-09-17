"""D2 proposal identities and bound business policy; no source or accepted objects."""
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
import json

from grid_case_generator.io.canonical_json import canonical_json_bytes

VERSION = 'synthetic-topology-proposals-v1'
RULE_VERSION = '1.0.0'
DECISION_SCHEMA = 'nanjing_completion_decisions_v1'


class ProposalClass(StrEnum):
    DETERMINISTIC_RECOVERY = 'DETERMINISTIC_RECOVERY'
    SYNTHETIC_ATTACHMENT_ELIGIBLE = 'SYNTHETIC_ATTACHMENT_ELIGIBLE'
    SYNTHETIC_DEVICE_ELIGIBLE = 'SYNTHETIC_DEVICE_ELIGIBLE'
    SYNTHETIC_BACKBONE_REQUIRED = 'SYNTHETIC_BACKBONE_REQUIRED'
    ROLE_CONFIRMATION_REQUIRED = 'ROLE_CONFIRMATION_REQUIRED'
    HARD_SOURCE_CONTRADICTION = 'HARD_SOURCE_CONTRADICTION'
    INSUFFICIENT_FOR_AUTOMATIC_PROPOSAL = 'INSUFFICIENT_FOR_AUTOMATIC_PROPOSAL'
    ALREADY_COMPLETE = 'ALREADY_COMPLETE'


def positive_voltage(value):
    if type(value) is not str:raise ValueError('voltage must be a decimal string in kV')
    try:d=Decimal(value)
    except InvalidOperation as exc:raise ValueError('invalid voltage') from exc
    if not d.is_finite() or d<=0:raise ValueError('voltage must be finite and positive')
    return d


def voltage_compatible(a,b):
    x,y=positive_voltage(a),positive_voltage(b)
    return x==y or {x,y}<={Decimal('10'),Decimal('10.5')}


def unknown_decision(case_id,feeder_id):
    return {'case_id':case_id,'feeder_id':feeder_id,'decision_version':'1.0.0','role':'UNKNOWN',
        'transformer_required':None,'synthetic_transformer_allowed':False,'synthetic_backbone_allowed':False,
        'nominal_voltage_kv':None,'lv_voltage_kv':None,'transformer_count':None,'demand_basis':None,
        'attachment_node_id':None,'confirmation_ref':None,'comment':None}


def _unique_keys(pairs):
    result={}
    for k,v in pairs:
        if k in result:raise ValueError('duplicate JSON key: '+k)
        result[k]=v
    return result


def parse_decisions(text,known_pairs,bindings):
    try:p=json.loads(text,object_pairs_hook=_unique_keys)
    except (TypeError,json.JSONDecodeError) as exc:raise ValueError('invalid decision JSON') from exc
    if not isinstance(p,dict) or set(p)!={'schema_version','decision_version','input_manifest_sha256','decisions'}:
        raise ValueError('decision root schema mismatch')
    if p['schema_version']!=DECISION_SCHEMA or not isinstance(p['decision_version'],str) or not p['decision_version'].strip():
        raise ValueError('decision version mismatch')
    if p['input_manifest_sha256']!=bindings:raise ValueError('stale decision input binding')
    if not isinstance(p['decisions'],list):raise ValueError('decisions must be array')
    seen=set();output=[]
    for r in p['decisions']:
        if not isinstance(r,dict) or set(r)!=set(unknown_decision('','')):raise ValueError('decision field schema mismatch')
        for key in ('case_id','feeder_id','decision_version'):
            if type(r[key]) is not str or not r[key].strip():raise ValueError('invalid decision identity/version')
        pair=(r['case_id'],r['feeder_id'])
        if pair not in known_pairs or pair in seen:raise ValueError('unknown/cross-case/duplicate decision identity')
        seen.add(pair)
        if r['role'] not in ('UNKNOWN','DISTRIBUTION_WITH_TRANSFORMER','NO_TRANSFORMER_REQUIRED'):raise ValueError('invalid role')
        for key in ('synthetic_transformer_allowed','synthetic_backbone_allowed'):
            if type(r[key]) is not bool:raise ValueError('permission must be boolean')
        if r['transformer_required'] is not None and type(r['transformer_required']) is not bool:raise ValueError('invalid transformer_required')
        for key in ('demand_basis','attachment_node_id','confirmation_ref','comment'):
            if r[key] is not None and (type(r[key]) is not str or not r[key].strip()):raise ValueError('invalid decision text')
        for key in ('nominal_voltage_kv','lv_voltage_kv'):
            if r[key] is not None:positive_voltage(r[key])
        if r['nominal_voltage_kv'] and r['lv_voltage_kv'] and positive_voltage(r['lv_voltage_kv'])>=positive_voltage(r['nominal_voltage_kv']):
            raise ValueError('LV must be below MV')
        if r['transformer_count'] is not None and (type(r['transformer_count']) is not int or r['transformer_count']<=0):
            raise ValueError('device count must be positive integer')
        if r['role']=='UNKNOWN':
            if any(r[k] is not None for k in ('transformer_required','nominal_voltage_kv','lv_voltage_kv','transformer_count','demand_basis','attachment_node_id')) or r['synthetic_transformer_allowed'] or r['synthetic_backbone_allowed']:
                raise ValueError('unknown role cannot grant permission')
        else:
            if not r['confirmation_ref']:raise ValueError('business confirmation source required')
            if r['role']=='DISTRIBUTION_WITH_TRANSFORMER' and r['transformer_required'] is not True:
                raise ValueError('distribution role requires transformer')
            if r['role']=='NO_TRANSFORMER_REQUIRED' and (r['transformer_required'] is not False or r['synthetic_transformer_allowed'] or r['transformer_count'] is not None):
                raise ValueError('no-transformer role contradicts device permission')
        if r['synthetic_transformer_allowed'] and (r['role']!='DISTRIBUTION_WITH_TRANSFORMER' or not all(r[k] for k in ('transformer_count','demand_basis','nominal_voltage_kv','lv_voltage_kv'))):
            raise ValueError('new Transformer requires role/count/demand/voltage confirmation')
        output.append(dict(r))
    return dict(p,decisions=sorted(output,key=lambda r:(r['case_id'],r['feeder_id'])))


def decision_bytes(policy):
    return canonical_json_bytes(dict(policy,decisions=sorted(policy['decisions'],key=lambda r:(r['case_id'],r['feeder_id']))))+b'\n'


def proposal_id(case_id,feeder_id,kind,semantic_key,config_hash):
    return 'proposal:'+sha256(canonical_json_bytes([VERSION,case_id,feeder_id,kind,semantic_key,config_hash])).hexdigest()
