// Deliberately configurable oracle host for runner negative controls.
import fs from 'node:fs';
import path from 'node:path';
const root=process.env.FAKE_SUITE, mode=process.env.FAKE_MODE, args=process.argv.slice(2);
function finish(code, value) { process.stdout.write(typeof value==='string'||Buffer.isBuffer(value)?value:'LMCODE_RETURN_BEGIN\n'+JSON.stringify({...value,message:value.message??'fixture error'})+'\nLMCODE_RETURN_END\n');process.exit(code); }
const usage=()=>finish(2,{ok:false,phase:'cli',code:'CLI_USAGE'});
if(args.length===1 && args[0]==='--version') finish(mode==='bad-cli'?1:0,'lmcode-fake-sample 0.1.0\n');
if(args[0]==='--lmcode-schema') { if(args.length>2 || args.length===2 && args[1]!=='--json') usage(); finish(0,fs.readFileSync(path.join(root,'sample.dsl.json'))); }
if(args.length===1 && args[0]==='--lmcode-signatures') {
 const s=JSON.parse(fs.readFileSync(path.join(root,'sample.dsl.json'))), out=[];
 for(const [n,t] of Object.entries(s.context)) out.push(`context ${n}: ${t}`);
 for(const [n,ds] of Object.entries(s.functions)) for(const d of ds) out.push(`fn ${n}(${d.params.join(', ')}) -> ${d.returns}`);
 for(const [o,t] of Object.entries(s.types)) for(const [n,ds] of Object.entries(t.methods)) for(const d of ds) out.push(`method ${o}.${n}(${d.params.join(', ')}) -> ${d.returns==='self'?o:d.returns}`);
 finish(0,out.sort().join('\n')+'\n');
}
if(args.length!==2 || args[0]!=='--lmcode') usage();
if(!fs.existsSync(args[1])) finish(4,{ok:false,phase:'app',code:'APP_FAIL'});
if(process.env.EXEC_MARKER) fs.writeFileSync(process.env.EXEC_MARKER,'ran');
const stem=path.basename(args[1],'.dslb');
let output=fs.readFileSync(path.join(root,'expected',stem+'.out'));
if(mode==='whitespace') output=Buffer.concat([output,Buffer.from(' ')]);
if(mode==='stderr') process.stderr.write('unexpected stderr');
const code=Number(fs.readFileSync(path.join(root,'expected',stem+'.exit')));
finish(code+(mode==='wrong-exit'?1:0),output);
