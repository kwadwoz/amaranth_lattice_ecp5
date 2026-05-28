"""
stub_core.py — fake solver that exists only to make the loop run end-to-end.

THIS IS NOT A REAL SAT SOLVER.

It uses brute-force enumeration and is limited to 20 variables so the loop
completes in bounded time. The point is to exercise the harness (parse →
build → program → run → Result), not to solve anything useful.

The real solver core will replace this later; the interface it exposes
(a single solve(cnf, timeout) method returning a Result) is frozen.
"""

from __future__ import annotations
import time
from itertools import product

from .contracts import CNF, Result, Status, Stats

MAX_VARS = 20   # brute-force limit — 2^20 = ~1 M iterations


class StubCore:
    """Brute-force stub solver. Enumerates all assignments up to MAX_VARS.

    Deliberately dumb — replace with real solver core later.
    The interface (solve method signature and return type) must stay stable.
    """

    def solve(self, cnf: CNF, timeout: float = 30.0) -> Result:
        if cnf.num_vars > MAX_VARS:
            return Result(
                status=Status.ERROR,
                error_msg=f"StubCore is limited to {MAX_VARS} variables "
                          f"(got {cnf.num_vars}). Use a real solver core.",
            )

        t0 = time.perf_counter()

        for values in product([False, True], repeat=cnf.num_vars):
            if time.perf_counter() - t0 > timeout:
                return Result(
                    status=Status.TIMEOUT,
                    stats=Stats(solve_time_s=time.perf_counter() - t0),
                )

            if self._satisfies(cnf.clauses, values):
                return Result(
                    status=Status.SAT,
                    assignment=list(values),   # index 0 = var 1, index N-1 = var N
                    stats=Stats(solve_time_s=time.perf_counter() - t0),
                )

        return Result(
            status=Status.UNSAT,
            stats=Stats(solve_time_s=time.perf_counter() - t0),
        )

    # INTERNALS 

    @staticmethod
    def _satisfies(clauses: list[list[int]], values: tuple[bool, ...]) -> bool:
        """Return True if `values` satisfies all clauses."""
        for clause in clauses:
            if not any(
                values[abs(lit) - 1] if lit > 0 else not values[abs(lit) - 1]
                for lit in clause
            ):
                return False
        return True