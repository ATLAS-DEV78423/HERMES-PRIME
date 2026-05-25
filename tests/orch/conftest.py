from pathlib import Path
import sys

_external_path = (
    Path(__file__).resolve().parent.parent.parent / "external" / "hermes-agent"
)
if str(_external_path) not in sys.path:
    sys.path.insert(0, str(_external_path))
