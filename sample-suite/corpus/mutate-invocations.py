#!/usr/bin/env python3
"""Compile genuine adapter faults in private copies; compile errors are not catches."""
from pathlib import Path
import os,shutil,subprocess,sys,tempfile,json
ROOT=Path(__file__).resolve().parent
repo=Path(sys.argv[1]).resolve();name=sys.argv[2]
with tempfile.TemporaryDirectory(prefix='sample-native-mutants-') as tmp:
 work=Path(tmp)/'host';shutil.copytree(repo,work,ignore=shutil.ignore_patterns('.git','build','__pycache__'))
 source=work/'src/main.cpp';original=source.read_text()
 def build():
  p=subprocess.run(['make','-j2'],cwd=work,capture_output=True);assert p.returncode==0,(p.stdout,p.stderr)
 def check(host):return subprocess.run([sys.executable,str(ROOT/'check-invocations.py'),str(host)],capture_output=True)
 build();host=work/'build'/name
 p=check(host);assert p.returncode==0,(p.stdout,p.stderr)
 print('PASS invocation mutation baseline',flush=True)
 ledger='host.domain.ledger' if name=='lmcode-c-sample' else 'host.ledger'
 mutants=[('lost summary','if(!failed)std::cout<<','if(false)std::cout<<','lost summary'),('reset shared context','Program program;',ledger+'.balance=0;'+ledger+'.entries=0;Program program;','ordered results/shared context/one process'),('wrong slot','results.select(part.index,host.registry,contract)','results.select(0,host.registry,contract)','ordered results/shared context/one process')]
 for label,anchor,replacement,diagnostic in mutants:
  assert original.count(anchor)==1,(label,'anchor');source.write_text(original.replace(anchor,replacement));build();p=check(host)
  assert p.returncode==1 and diagnostic.encode() in p.stderr,(label,p.stdout,p.stderr)
  print('CAUGHT '+label,flush=True)
 source.write_text(original);build()
 # Real subprocess-per-file fault: the wrapper removes metadata in each child,
 # preserving its normal single-program protocol. The builder must refuse it.
 wrapper=Path(tmp)/'per-file-host'
 wrapper.write_text('#!'+shutil.which('python3')+'\n'+'''import sys,subprocess,os
host='''+repr(str(host))+'''
a=sys.argv[1:]
if a and a[0].startswith('--lmcode-'):sys.exit(subprocess.call([host,*a]))
codes=[]
for i in range(0,len(a),2):
 p=subprocess.run([host,'--lmcode',a[i+1]],env={k:v for k,v in os.environ.items() if k!='LMCODE_INVOCATION_FILE'},capture_output=True)
 sys.stdout.buffer.write(p.stdout);sys.stderr.buffer.write(p.stderr);codes.append(p.returncode)
sys.exit(next((c for c in codes if c),0))
''');wrapper.chmod(0o755)
 p=check(wrapper);assert p.returncode==1 and b'AssertionError' in p.stderr,(p.stdout,p.stderr)
 print('CAUGHT real per-file process',flush=True)
