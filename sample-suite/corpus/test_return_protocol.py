"""Frame oracle controls; expected payloads never come from recorded stdout."""
import json
from pathlib import Path
import runpy
import subprocess
import unittest
ROOT=Path(__file__).resolve().parent
validate=runpy.run_path(str(ROOT/'return_protocol.py'))['validate']
DIAG=b'{"host_summary":{}}\n'
def frame(value):return DIAG+b'LMCODE_RETURN_BEGIN\n'+json.dumps({"ok":True,"result":value},ensure_ascii=False).encode()+b'\nLMCODE_RETURN_END\n'
class FrameOracle(unittest.TestCase):
    def both(self, output, code, expected=None, good=True):
        if good:validate(output,code,expected)
        else:
            with self.assertRaises((ValueError,UnicodeError)):validate(output,code,expected)
        p=subprocess.run(['node',str(ROOT/'bytes.mjs')],input=json.dumps({'op':'validate-return','hex':output.hex(),'code':code,'expected':expected}).encode(),capture_output=True)
        self.assertEqual(p.returncode==0,good,p.stderr.decode(errors='replace'))
    def test_null_and_shortest_float(self):
        self.both(frame(None),0)
        self.both(frame(0.30000000000000004),0,0.30000000000000004)
    def test_nested_owned_values_and_marker_data(self):
        value={'rows':[[1,True,None]],'marker':'LMCODE_RETURN_BEGIN\n水'}
        self.both(frame(value),0,value)
    def test_missing_frame(self):self.both(DIAG,0,good=False)
    def test_duplicate_frame(self):self.both(frame(None)+frame(None),0,good=False)
    def test_trailing_bytes(self):self.both(frame(None)+b' ',0,good=False)
    def test_crlf(self):self.both(frame(None).replace(b'\n',b'\r\n'),0,good=False)
    def test_reset_result(self):self.both(frame({'entry':1}),0,{'body':1,'entry':1},good=False)
    def test_wrong_nested_type(self):self.both(frame({'flag':1}),0,{'flag':True},good=False)
    def test_failed_invocation_cannot_frame(self):
        self.both(b'LMCODE_RETURN_BEGIN\n{"ok":false,"phase":"run","code":"RUN_HOST","message":"bad"}\nLMCODE_RETURN_END\n',3)
        self.both(frame(None),3,good=False)
    def test_invalid_utf8(self):self.both(DIAG+b'LMCODE_RETURN_BEGIN\n"\xff"\nLMCODE_RETURN_END\n',0,'x',good=False)
if __name__=='__main__':unittest.main()
