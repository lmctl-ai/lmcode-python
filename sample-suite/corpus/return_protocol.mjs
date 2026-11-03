// Independent frame and summary oracle; never infer the expected return value.
export function validateReturn(hex, code, expected=null) {
 const text=new TextDecoder('utf-8',{fatal:true}).decode(Buffer.from(hex,'hex')),lines=text.split('\n');
 if(lines.at(-1)!==''||lines.at(-2)!=='LMCODE_RETURN_END'||lines.at(-4)!=='LMCODE_RETURN_BEGIN'||lines.filter(x=>x==='LMCODE_RETURN_BEGIN').length!==1||lines.filter(x=>x==='LMCODE_RETURN_END').length!==1||lines.slice(-4).join('').includes('\r'))throw Error('missing, duplicate or nonterminal invocation frame');
 const v=JSON.parse(lines.at(-3));if(!v||typeof v!=='object'||typeof v.ok!=='boolean')throw Error('envelope required');
 if(code){if(v.ok||Object.keys(v).some(k=>!['ok','phase','code','message','line','column','part'].includes(k))||!['phase','code','message'].every(k=>typeof v[k]==='string')||({cli:2,load:3,run:3,app:4})[v.phase]!==code)throw Error('invalid failure envelope');}
 else {if(!v.ok||Object.keys(v).join(',')!=='ok,result'||JSON.stringify(v.result)!==JSON.stringify(expected))throw Error('result differs from oracle');if(Object.keys(JSON.parse(lines.at(-5))).join(',')!=='host_summary')throw Error('missing tagged host summary');}
 return true;
}
