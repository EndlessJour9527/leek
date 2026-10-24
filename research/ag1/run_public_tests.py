"""Explicit public subset: legacy recovery-record checks require private evidence."""
import sys
import unittest
from pathlib import Path
root = Path(__file__).resolve().parent / "implementation"
sys.path.insert(0, str(root))
excluded = {"test_batch_artifacts", "test_release_gate"}
suite = unittest.TestSuite()
for path in sorted(root.glob("test_*.py")):
    if path.stem not in excluded:
        suite.addTests(unittest.defaultTestLoader.loadTestsFromName(path.stem))
print("Excluded 5 legacy checks in test_batch_artifacts / test_release_gate: private recovery evidence absent", flush=True)
sys.exit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
