from __future__ import annotations

import logging
import os
import signal
import sys
import threading
from types import FrameType
from typing import Any, Callable

logger = logging.getLogger(__name__)

_shutdown_requested = threading.Event()


def shutdown_requested() -> bool:
    return _shutdown_requested.is_set()


def _signal_handler(signum: int, _frame: FrameType | None) -> None:
    signame = signal.Signals(signum).name
    logger.warning("Received signal %s, initiating graceful shutdown...", signame)
    _shutdown_requested.set()


def install_signal_handlers() -> None:
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)


def safe_main(main_fn: Callable[[], int]) -> int:
    install_signal_handlers()
    try:
        return main_fn()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 130
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1
    except Exception as exc:
        logger.exception("Unhandled exception in main: %s", exc)
        print(f"\n[FATAL] {exc}", file=sys.stderr)
        return 1
    finally:
        _shutdown_requested.clear()
