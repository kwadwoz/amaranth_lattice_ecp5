"""
sim_backend.py — pure-software backend, no hardware required.

Stores whatever core is passed to build(), then delegates run() directly
to core.solve(). No synthesis, no UART, no board.

This is the backend the agent uses when no hardware is present, and the
one that makes pytest pass without a board attached.
"""

from __future__ import annotations

from .contracts import CNF, Result, Status
from .fpga_interface import FPGAInterface


class SimBackend(FPGAInterface):

    def __init__(self) -> None:
        self._core = None

    def build(self, core) -> None:
        """Store the core — no synthesis needed for simulation."""
        self._core = core

    def program(self) -> None:
        """No-op — nothing to flash in simulation."""

    def run(self, cnf: CNF, timeout: float = 30.0) -> Result:
        """Hand the CNF directly to the stored core and return its Result."""
        if self._core is None:
            return Result(
                status=Status.ERROR,
                error_msg="No core loaded. Call build(core) before run().",
            )
        try:
            return self._core.solve(cnf, timeout)
        except Exception as exc:
            return Result(status=Status.ERROR, error_msg=str(exc))
