from __future__ import annotations

import threading
from pathlib import Path
from typing import Any


class GatewayManager:
    """Governed messaging gateway manager wrapping upstream gateway."""

    def __init__(self, workspace_root: str | Path, sentinel: Any = None, trust_store: Any = None):
        self.workspace_root = Path(workspace_root).resolve()
        self.sentinel = sentinel
        self.trust_store = trust_store
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self, platforms: list[str] | None = None) -> dict[str, Any]:
        if self._running:
            return {"status": "already running", "platforms": platforms or ["all"]}
        try:
            from gateway.run import run_gateway
            platforms = platforms or ["slack"]
            self._thread = threading.Thread(
                target=run_gateway,
                kwargs={"platforms": platforms},
                daemon=True,
            )
            self._thread.start()
            self._running = True
            return {"status": "started", "platforms": platforms}
        except ImportError:
            return {"error": "Upstream gateway not available"}
        except Exception as e:
            return {"error": str(e)}

    def stop(self) -> dict[str, Any]:
        if not self._running:
            return {"status": "not running"}
        try:
            from gateway.run import stop_gateway
            stop_gateway()
            self._running = False
            return {"status": "stopped"}
        except ImportError:
            return {"error": "Upstream gateway not available"}

    def status(self) -> dict[str, Any]:
        try:
            from gateway.run import gateway_status
            return gateway_status()
        except ImportError:
            return {"status": "upstream gateway not available"}

    def list_platforms(self) -> list[dict[str, Any]]:
        try:
            from pathlib import Path as P
            platforms_dir = Path(__file__).parent.parent / "external" / "hermes-agent" / "gateway" / "platforms"
            if not platforms_dir.exists():
                return [{"error": "Platforms directory not found"}]
            result = []
            for f in sorted(platforms_dir.glob("*.py")):
                if f.name.startswith("_"):
                    continue
                name = f.stem
                result.append({"name": name, "file": str(f)})
            return result
        except Exception as e:
            return [{"error": str(e)}]
