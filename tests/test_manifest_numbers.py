"""WP186 regression tests for supported public behavior."""
import unittest
from lmcode import InvocationResults


class ManifestNumbers(unittest.TestCase):
    def test_integral_manifest_tokens(self):
        for version in ("1", "1.0", "1e0", "10e-1"):
            for index in ("0", "0.0", "0e0", "-0.0", "0e9999"):
                with self.subTest(version=version, index=index):
                    raw = ('{"version":'+version+',"mode":"single","dry":false,"parts":[{"index":'+index+',"file":"/tmp/a"}]}').encode()
                    result = InvocationResults.from_metadata(raw, ["/tmp/a"])
                    self.assertEqual(result.registrations_copy()[0].index, 0)

    def test_manifest_rejections_keep_pointer_diagnostics(self):
        for token, reason in (("1e-9999", "underflow"), ("9007199254740992", "unsafe_integer"), ("9007199254740992.0", "unsafe_integer")):
            with self.subTest(token=token):
                raw = ('{"version":1,"mode":"single","dry":true,"parts":[{"index":'+token+',"file":"/tmp/a"}]}').encode()
                with self.assertRaisesRegex(Exception, "/parts/0/index: " + reason) as caught:
                    InvocationResults.from_metadata(raw, ["/tmp/a"])
                self.assertEqual(caught.exception.code, "CLI_USAGE")
                self.assertTrue(caught.exception.invocation_dry)
        for token in ("true", "0.5", "null"):
            raw = ('{"version":1,"mode":"single","dry":false,"parts":[{"index":'+token+',"file":"/tmp/a"}]}').encode()
            with self.assertRaisesRegex(Exception, "noncontiguous index") as caught:
                InvocationResults.from_metadata(raw, ["/tmp/a"])
            self.assertEqual(caught.exception.code, "CLI_USAGE")


if __name__ == "__main__":
    unittest.main()
