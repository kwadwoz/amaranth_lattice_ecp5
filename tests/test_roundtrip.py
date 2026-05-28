"""
test_roundtrip.py — proves the full loop works end-to-end without hardware.

Tests:
  - SAT result is returned with a valid assignment
  - The assignment actually satisfies the formula (stand-in host-side verifier)
  - UNSAT result carries no assignment
  - Trivial single-variable case works
  - solve_sat() works from a DIMACS file on disk
  - Hardware backend raises NotImplementedError (documents hw is deferred)
  - Every result carries timing stats
"""

import os
import tempfile
import pytest

from infrastructure.contracts import CNF, Status
from infrastructure.sim_backend import SimBackend
from infrastructure.stub_core import StubCore
from infrastructure.ecp5_uart_backend import ECP5UARTBackend



# Inline test formulas


# (x1 v x2) ^ (~x1 v x3) ^ (~x2 v ~x3)  — SAT
SAT_CNF = CNF(num_vars=3, clauses=[[1, 2], [-1, 3], [-2, -3]])

# (x1 v x2) ^ (~x1 v x2) ^ (x1 v ~x2) ^ (~x1 v ~x2)  — UNSAT
UNSAT_CNF = CNF(num_vars=2, clauses=[[1, 2], [-1, 2], [1, -2], [-1, -2]])

# Single clause forcing x1=True  — trivially SAT
TRIVIAL_CNF = CNF(num_vars=1, clauses=[[1]])



# Stand-in host-side verifier
# Checks a returned assignment actually satisfies the formula.
# The real verifier is out of scope for this task (owned by teammate).


def satisfies(cnf: CNF, assignment: list[bool]) -> bool:
    """Return True if assignment satisfies every clause in cnf."""
    for clause in cnf.clauses:
        if not any(
            assignment[abs(lit) - 1] if lit > 0 else not assignment[abs(lit) - 1]
            for lit in clause
        ):
            return False
    return True



# Helpers


def make_sim() -> SimBackend:
    backend = SimBackend()
    backend.build(StubCore())
    backend.program()
    return backend



# SimBackend tests


def test_sat_status():
    result = make_sim().run(SAT_CNF, timeout=5.0)
    assert result.status == Status.SAT


def test_sat_assignment_present():
    result = make_sim().run(SAT_CNF, timeout=5.0)
    assert result.assignment is not None
    assert len(result.assignment) == SAT_CNF.num_vars


def test_sat_assignment_satisfies_formula():
    result = make_sim().run(SAT_CNF, timeout=5.0)
    assert result.status == Status.SAT
    assert satisfies(SAT_CNF, result.assignment)


def test_unsat_status():
    result = make_sim().run(UNSAT_CNF, timeout=5.0)
    assert result.status == Status.UNSAT


def test_unsat_has_no_assignment():
    result = make_sim().run(UNSAT_CNF, timeout=5.0)
    assert result.assignment is None


def test_trivial_sat():
    result = make_sim().run(TRIVIAL_CNF, timeout=5.0)
    assert result.status == Status.SAT
    assert satisfies(TRIVIAL_CNF, result.assignment)


def test_result_carries_timing():
    result = make_sim().run(SAT_CNF, timeout=5.0)
    assert result.stats is not None
    assert result.stats.solve_time_s >= 0.0


def test_error_when_no_core_loaded():
    backend = SimBackend()  # build() never called
    result = backend.run(SAT_CNF, timeout=5.0)
    assert result.status == Status.ERROR
    assert result.error_msg is not None


# solve_sat() from a DIMACS file


DIMACS_SAT = """\
c simple SAT: (x1 v ~x2) ^ (x2 v x3)
p cnf 3 2
1 -2 0
2 3 0
"""

DIMACS_UNSAT = """\
c UNSAT: x1 ^ ~x1
p cnf 1 2
1 0
-1 0
"""


def test_solve_sat_from_file_sat():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.cnf', delete=False) as f:
        f.write(DIMACS_SAT)
        path = f.name
    try:
        result = make_sim().solve_sat(path, core=StubCore(), timeout=5.0)
        assert result.status == Status.SAT
    finally:
        os.unlink(path)


def test_solve_sat_from_file_unsat():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.cnf', delete=False) as f:
        f.write(DIMACS_UNSAT)
        path = f.name
    try:
        result = make_sim().solve_sat(path, core=StubCore(), timeout=5.0)
        assert result.status == Status.UNSAT
    finally:
        os.unlink(path)


def test_solve_sat_bad_path_returns_error():
    result = make_sim().solve_sat("/nonexistent/path.cnf", core=StubCore())
    assert result.status == Status.ERROR
    assert result.error_msg is not None


# Hardware backend — documents that hardware is intentionally deferred


def test_hw_build_raises():
    with pytest.raises(NotImplementedError):
        ECP5UARTBackend().build(StubCore())


def test_hw_program_raises():
    with pytest.raises(NotImplementedError):
        ECP5UARTBackend().program()


def test_hw_run_raises():
    with pytest.raises(NotImplementedError):
        ECP5UARTBackend().run(SAT_CNF, timeout=5.0)