"""Coverage hook for the Studio tests. Put this folder on PYTHONPATH and set COVERAGE_PROCESS_START so that Python
subprocesses started by the tests (the fake bridge, studio.py --fake) write coverage data too. See docs/TESTING.md."""
try:
    import coverage
    coverage.process_startup()
except Exception:
    pass
