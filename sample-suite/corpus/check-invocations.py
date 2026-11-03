#!/usr/bin/env python3
"""Real public compiler-to-native integration with a direct raw-frame control."""
import json,os,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def check(host):
 with tempfile.TemporaryDirectory(prefix='sample-invocation-') as tmp:
  host_path=Path(host)
  if os.name=='nt' and not host_path.is_file() and host_path.suffix.lower()!='.exe':
   host_path=host_path.with_suffix('.exe')
  host=str(host_path.resolve())
  source=Path(tmp)/'real.lms'
  source.write_text((ROOT/'invocations.lms').read_text().replace('"__HOST__"',json.dumps(host)))
  p=subprocess.run([os.environ.get('LMSCRIPT_BIN','lmscript'),str(source),str(host_path.resolve())],capture_output=True)
 if p.returncode!=0 or b'PASS real single/builder' not in p.stdout:raise AssertionError((p.returncode,p.stdout,p.stderr))
 if p.stdout.count(b'"host_summary":')!=8:raise AssertionError(('lost summary',p.stdout))
 direct=subprocess.run([host,'--lmcode',str(ROOT/'bytecode/068-rule-entries.dslb')],capture_output=True)
 if direct.returncode!=0:raise AssertionError(('direct host baseline',direct.returncode,direct.stdout,direct.stderr))
 lines=direct.stdout.splitlines()
 begins=[i for i,line in enumerate(lines) if line==b'LMCODE_RETURN_BEGIN']
 ends=[i for i,line in enumerate(lines) if line==b'LMCODE_RETURN_END']
 if len(begins)!=1 or len(ends)!=1 or ends[0]!=begins[0]+2:raise AssertionError(('direct host frame shape',direct.stdout))
 bare=b'{"ok":true,"result":null}'
 if any(line==bare for i,line in enumerate(lines) if i<begins[0] or i>ends[0]):raise AssertionError(('stale bare frame',direct.stdout))
 print('PASS public single/builder native integration, eight summaries and one direct terminal frame')

if __name__=='__main__':check(sys.argv[1])
