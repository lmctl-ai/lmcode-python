"""Independent invocation envelope/summary oracle, before recording expectations."""
import json
BEGIN=b'LMCODE_RETURN_BEGIN\n';END=b'LMCODE_RETURN_END\n'
def validate(stdout, code, expected=None):
    lines=stdout.splitlines(keepends=True)
    if len(lines)<3 or lines[-3]!=BEGIN or lines[-1]!=END or lines.count(BEGIN)!=1 or lines.count(END)!=1:
        raise ValueError('missing, duplicate or nonterminal invocation frame')
    if b'\r' in b''.join(lines[-3:]):raise ValueError('frame must use LF bytes')
    value=json.loads(lines[-2].decode('utf8'))
    if not isinstance(value,dict) or type(value.get('ok')) is not bool:raise ValueError('envelope required')
    if code:
        if set(value)-{'ok','phase','code','message','line','column','part'} or value['ok'] or any(k not in value for k in ['phase','code','message']):raise ValueError('failure envelope has payload or missing fields')
        if {'cli':2,'load':3,'run':3,'app':4}.get(value['phase'])!=code:raise ValueError('failure phase/exit mismatch')
    else:
        if set(value)!={'ok','result'} or not value['ok']:raise ValueError('single success envelope shape')
        if json.dumps(value['result'],sort_keys=True)!=json.dumps(expected,sort_keys=True):raise ValueError('result differs from independent oracle')
        if len(lines)<4 or set(json.loads(lines[-4]))!={'host_summary'}:raise ValueError('missing tagged host summary')
    return value
