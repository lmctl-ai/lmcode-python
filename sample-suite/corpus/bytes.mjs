// Binary/process adapter only. Test selection and assertions live in .lms files.
import fs from 'node:fs';
import {validateReturn} from './return_protocol.mjs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawnSync} from 'node:child_process';
const q = JSON.parse(fs.readFileSync(0, 'utf8'));
const hash = p => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
let value;
if (q.op === 'validate-return') value = validateReturn(q.hex, q.code, q.expected);
else if (q.op === 'hashes') value = q.paths.map(hash);
else if (q.op === 'hex') value = fs.readFileSync(q.path).toString('hex');
else if (q.op === 'temp') value = fs.mkdtempSync(path.join(os.tmpdir(), 'lmcode-suite-'));
else if (q.op === 'copy') { fs.cpSync(q.from, q.to, {recursive:true}); value = true; }
else if (q.op === 'imports') {
  const b = fs.readFileSync(q.path); let p = 38;
  const u32 = () => { const n=b.readUInt32BE(p); p+=4; return n; };
  const constants=[]; const count=u32();
  for(let i=0;i<count;i++) { if(b[p++]!==1) throw Error('bad constant tag'); const n=u32(); constants.push(b.subarray(p,p+n).toString('utf8'));p+=n; }
  const n=b.readUInt16BE(p);p+=2; value=[];
  for(let i=0;i<n;i++) value.push(constants[u32()]);
} else if (q.op === 'mutate') {
  let b=fs.readFileSync(q.source);
  if(q.mutation.byte_offset !== undefined) b[q.mutation.byte_offset] ^= 255;
  else if(q.mutation.bytecode_version !== undefined) b.writeUInt16BE(q.mutation.bytecode_version,4);
  else { const before=Buffer.from(q.mutation.import_from), after=Buffer.from(q.mutation.import_to); if(before.length!==after.length || b.indexOf(before)<0) throw Error('missing import mutation'); for(let p=b.indexOf(before);p>=0;p=b.indexOf(before,p+after.length)) after.copy(b,p); }
  fs.writeFileSync(q.output,b); value=true;
} else if(q.op === 'run') {
  const scratch=fs.mkdtempSync(path.join(os.tmpdir(),'lmcode-case-'));
  try {
    for(const [name,hex] of Object.entries(q.fixtures || {})) {
      if(path.basename(name)!==name || name.includes('\\') || name==='..') throw Error('unsafe fixture name');
      fs.writeFileSync(path.join(scratch,name),Buffer.from(hex,'hex'));
    }
    // npm installs Windows command shims; invoke their JS entry without a shell.
    let argv=[...q.argv];
    if(process.platform==='win32' && /^(lmscript|lmctl)(\.cmd)?$/.test(path.basename(argv[0]))) {
      const name=path.basename(argv[0]).replace(/\.cmd$/,'');
      const dirs=path.isAbsolute(argv[0]) ? [path.dirname(argv[0])] : (process.env.PATH || '').split(path.delimiter);
      const dir=dirs.find(d=>fs.existsSync(path.join(d,name+'.cmd')));
      if(!dir) throw Error('npm executable not found: '+name);
      const shim=fs.readFileSync(path.join(dir,name+'.cmd'),'utf8');
      const match=shim.match(/%dp0%[\\/]([^"\r\n]+)"\s+%\*/i);
      if(!match) throw Error('unsupported npm shim: '+name);
      argv=[process.execPath,path.resolve(dir,match[1].replaceAll('\\','/')),...argv.slice(1)];
    }
    const r=spawnSync(argv[0],argv.slice(1),{cwd:q.cwd,env:{...process.env,SAMPLE_TMP:scratch},timeout:q.timeout || 30000,maxBuffer:16*1024*1024});
    value={code:r.status,stdout:(r.stdout||Buffer.alloc(0)).toString('utf8'),stderr:(r.stderr||Buffer.alloc(0)).toString('utf8'),hex:(r.stdout||Buffer.alloc(0)).toString('hex'),stderr_hex:(r.stderr||Buffer.alloc(0)).toString('hex'),error:r.error?.message || '',signal:r.signal};
  } finally { fs.rmSync(scratch,{recursive:true,force:true}); }
} else throw Error('unknown operation');
process.stdout.write(JSON.stringify(value));
