import sys
import pathlib

# Determine the path to the actual package implementation under src/fleet_memory.
_src_root = pathlib.Path(__file__).resolve().parents[1] / "src"
_fleet_path = _src_root / "fleet_memory"

# Ensure the implementation directory is on sys.path for submodule imports.
if str(_fleet_path) not in sys.path:
    sys.path.insert(0, str(_fleet_path))

# Make this package's __path__ point to the real implementation directory so that
# imports like ``import fleet_memory.reindex`` resolve correctly.
__path__ = [_fleet_path.as_posix()]
