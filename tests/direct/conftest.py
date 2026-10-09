from pathlib import Path

import pytest

from gltest.direct.sdk_loader import setup_sdk_paths

_CONTRACT = Path(__file__).resolve().parents[2] / 'contracts/rainhedge.py'

# Module-level arm (historic behavior): make the runner's SDK paths
# importable before any test runs.
setup_sdk_paths(_CONTRACT)


@pytest.fixture(autouse=True)
def _rearm_sdk_paths():
    """Re-arm the gltest-direct SDK paths for EVERY test.

    gltest's direct-mode teardown evicts every module loaded from the
    SDK paths and strips those paths from sys.path after each test, but
    setup_sdk_paths() only ran once at conftest import. Tests after the
    first would then hit `from genlayer.py.types import Address`
    ImportError inside create_address() and silently receive RAW BYTES
    instead of Address objects ('bytes' has no attribute 'as_hex').
    Re-running setup (cached extraction, path-insert is idempotent)
    before each test restores the documented per-test isolation the
    fixtures assume.
    """
    setup_sdk_paths(_CONTRACT)
    yield
