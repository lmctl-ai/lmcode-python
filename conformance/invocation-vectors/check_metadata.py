"""Shared exact-byte malformed-metadata oracle for native collector runners."""
import json,os,subprocess,tempfile
from pathlib import Path

def check(command,folder):
 folder=Path(folder)
 with tempfile.TemporaryDirectory(prefix='metadata-byte-goldens-') as temporary:
  path=Path(temporary)/'invocation.json'
  for case in json.loads((folder/'metadata-errors.json').read_text()):
   path.write_bytes(bytes.fromhex(case['raw_hex']))
   result=subprocess.run([*command,str(folder/'schema.json'),str(folder/'single-null.json'),'/unused'],env=dict(os.environ,LMCODE_INVOCATION_FILE=str(path)),capture_output=True)
   assert (result.returncode,result.stdout,result.stderr)==(2,case['frame'].encode(),b''),(case['name'],result)
   print('PASS metadata bytes',case['name'])
