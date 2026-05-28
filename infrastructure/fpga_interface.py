"""
fpga_interface.py — abstract base class defining the contract every backend must satisfy.

Key architectural decision: build() takes a *solver core*, not a full design.
The untouched communication layer (UART framing, protocol parsing) wraps the core
before synthesis. The agent can only ever provide the solving logic — it cannot
touch or overwrite the communication pins.

Backends implement three primitives:
    build(core)          — load / compile the solver core
    program()            — flash the last build to the target (no-op for sim)
    run(cnf, timeout)    — execute and return a Result

solve_sat() is a concrete template method on this base class.
Backends must NOT reimplement it — all orchestration lives here exactly once.
"""

from __future__ import annotations
from abc import ABC, abstractmethod

from .contracts import CNF, Result, Status, read_dimacs


class FPGAInterface(ABC):

    
    # Primitives — every backend must implement exactly these three
    

    @abstractmethod
    def build(self, core) -> None:
        """Load or compile the solver core.

        The implementation wraps `core` inside the frozen communication
        shell before any synthesis step. Callers never provide I/O or
        comm logic — only the solving kernel.
        """

    @abstractmethod
    def program(self) -> None:
        """Flash the last built artefact to the target device.

        No-op for simulation backends.
        """

    @abstractmethod
    def run(self, cnf: CNF, timeout: float) -> Result:
        """Execute the loaded design on `cnf` and return a Result.

        Must return Result(status=Status.TIMEOUT) if `timeout` seconds
        elapse before completion, and Result(status=Status.ERROR) for
        any harness-level failure — never raise for expected conditions.
        """

   
    # Template method — implemented once here, never in subclasses
   

    def solve_sat(self, cnf_path: str, core, timeout: float = 30.0) -> Result:
        """Parse a DIMACS file then build, program, and run in one call.

        This is the single entry point the agent will use. The orchestration
        order (parse → build → program → run) is frozen here; backends
        only supply the three primitives above.
        """
        try:
            cnf = read_dimacs(cnf_path)
        except Exception as exc:
            return Result(status=Status.ERROR, error_msg=f"DIMACS parse error: {exc}")

        self.build(core)
        self.program()
        return self.run(cnf, timeout)