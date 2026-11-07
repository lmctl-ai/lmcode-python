#!/usr/bin/env python3
"""Replay the shared REST suite in memory and through a real child process (stdin/stdout)."""
import pathlib, sys, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import rest_replay as replay


class Runner(unittest.TestCase):
    def runTest(self):
        self.counts = (replay.replay(self, replay.serve_in_memory), replay.replay(self, replay.serve_process))


def main():
    case = Runner()
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=0).run(case)
    if not result.wasSuccessful():
        print("FAIL rest suite")
        return 1
    memory, process = case.counts
    print("PASS rest conformance: %d/%d in-memory, %d/%d via child process stdin/stdout" % (memory, memory, process, process))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
