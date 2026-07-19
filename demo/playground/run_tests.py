#!/usr/bin/env python3
"""Run Bittu's game tests and print a big, judge-visible banner.
No dependencies beyond the Python stdlib — safe on any venue laptop."""
import sys
import unittest

GREEN = "\033[1;32m"
RED = "\033[1;31m"
RESET = "\033[0m"


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=".", pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    ok = result.wasSuccessful()
    passed = result.testsRun - len(result.failures) - len(result.errors)
    color = GREEN if ok else RED
    label = "ALL TESTS PASSED" if ok else "TESTS FAILING"
    bar = "=" * 50

    print()
    print(f"{color}{bar}")
    print(f"  {label}   ({passed}/{result.testsRun} green)")
    print(f"{bar}{RESET}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
