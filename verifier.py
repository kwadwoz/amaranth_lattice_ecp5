"""
verifier.py — correctness oracle for the FPGA SAT accelerator.

This module checks whether the FPGA's answer is actually correct, and is the thing
that catches a hardware bug where the solver returns a wrong result.

How it connects to the rest of the project:
    - parse_dimacs()    (in sat_experiment.py) gives us `clauses`
    - decode_response() (in sat_experiment.py) gives us `result`, a dict like
          {'result': 'SAT', 'assignment': {1: True, 2: False, ...}}
          {'result': 'UNSAT'}
          {'result': 'TIMEOUT'}
    - this module takes those two things and returns a Verdict

Two kinds of check, because SAT and UNSAT aren't symmetric:
    SAT   -> witness check. Plug the assignment into the formula.
    UNSAT -> cross-check against a trusted independent solver (DPLL.py). Only
             meaningful once the FPGA runs a real, separate solver; until then it
             just confirms the two solvers agree.
"""

from typing import Optional

# We reuse the satisfaction logic and the reference solver from DPLL.py.
from DPLL import clause_status, formula_status, dpll


# verdict outcomes
# These mirror the three outcome codes in the design doc.
VERIFIED              = "VERIFIED"               # the FPGA's answer is correct
FALSIFIED             = "FALSIFIED"              # the FPGA's answer is WRONG (bug)
NOT_APPLICABLE        = "NOT_APPLICABLE"         # nothing to verify (e.g. timeout)
CORRECTNESS_VIOLATION = "CORRECTNESS_VIOLATION"  # FPGA confidently returned a wrong answer


def _all_variables(clauses: list[list[int]]) -> set[int]:
    """Every variable index that appears anywhere in the formula."""
    return {abs(lit) for clause in clauses for lit in clause}


def _complete_assignment(assignment: dict[int, bool],
                         clauses: list[list[int]],
                         default: bool = False) -> dict[int, bool]:
    """Fill in any variable the FPGA left unset, defaulting it.

    Unset variables are 'don't cares' only if the formula is already satisfied
    without them. We default them so formula_status can return a clean
    True/False instead of None.
    """
    full = dict(assignment)  # copy, don't mutate the caller's dict
    for var in _all_variables(clauses):
        if var not in full:
            full[var] = default
    return full


def find_falsified_clause(clauses: list[list[int]],
                          assignment: dict[int, bool]) -> Optional[list[int]]:
    """Return the first clause that is FALSE under the assignment, or None.

    A clause is false when every one of its literals is false. This is the
    evidence we attach when an assignment fails verification.
    """
    for clause in clauses:
        if clause_status(clause, assignment) is False:
            return clause
    return None


# the SAT branch

def verify_sat(clauses: list[list[int]],
               assignment: dict[int, bool]) -> dict:
    """Check that a claimed satisfying assignment actually satisfies the formula.

    Returns a dict with the verdict and, on failure, the offending clause.
    """
    # Complete any unset variables so the check is definitive (no None).
    full = _complete_assignment(assignment, clauses)

    status = formula_status(clauses, full)

    if status is True:
        return {"verdict": VERIFIED}

    # status is False (or None, which _complete_assignment should have ruled out).
    # The FPGA said SAT and handed us an assignment that does not satisfy the
    # formula. That is a real correctness bug in the hardware.
    bad = find_falsified_clause(clauses, full)
    return {
        "verdict": CORRECTNESS_VIOLATION,
        "reason": "FPGA returned SAT but the assignment does not satisfy the formula",
        "falsified_clause": bad,
    }


# the UNSAT branch

def verify_unsat(clauses: list[list[int]]) -> dict:
    """Cross-check a claimed UNSAT against the trusted reference solver.

    We cannot witness-check UNSAT (there is no assignment to plug in), so we ask
    an independent trusted solver. If DPLL also says UNSAT, we trust it. If DPLL
    finds a satisfying assignment, the FPGA was WRONG (it claimed no solution
    exists, but one does), and we return that assignment as the counterexample.

    NOTE: this is only a meaningful correctness test when the FPGA runs a solver
    that is independent of DPLL. While the FPGA solver does not yet exist, this
    branch confirms plumbing, not correctness.

    Only feasible on small instances where DPLL can keep up. Large instances
    would need a proof-based check (DRAT), which is out of scope for now.
    """
    ref_result, witness = dpll(list(clauses))  # DPLL prints a trace; fine for now

    if ref_result == "unsat":
        return {"verdict": VERIFIED}

    # DPLL found a satisfying assignment -> the FPGA's UNSAT was wrong.
    return {
        "verdict": CORRECTNESS_VIOLATION,
        "reason": "FPGA returned UNSAT but a satisfying assignment exists",
        "counterexample": witness,
    }


# top-level entry point

def verify(clauses: list[list[int]], result: dict,
           cross_check_unsat: bool = True) -> dict:
    """Verify an FPGA result against the formula.

    Args:
        clauses: the formula, produced by parse_dimacs()
        result:  the dict produced by decode_response()
        cross_check_unsat: if False, skip the DPLL cross-check for UNSAT and
            just mark it NOT_APPLICABLE (useful while no real
            independent FPGA solver exists, to avoid the
            circular check).

    Returns a dict with at least a "verdict" key.
    """
    outcome = result.get("result")

    if outcome == "SAT":
        return verify_sat(clauses, result.get("assignment", {}))

    if outcome == "UNSAT":
        if cross_check_unsat:
            return verify_unsat(clauses)
        return {"verdict": NOT_APPLICABLE,
                "reason": "UNSAT cross-check disabled (no independent solver yet)"}

    if outcome == "TIMEOUT":
        return {"verdict": NOT_APPLICABLE, "reason": "solver timed out"}

    return {"verdict": NOT_APPLICABLE, "reason": f"unrecognized result: {outcome}"}


# self-test
# These test the verifier itself, using hand-made answers. No FPGA, no real
# solver needed. We feed it correct and wrong answers and confirm
# it catches them.

if __name__ == "__main__":
    # F = (x1 v x2) ^ (-x1 v x3) ^ (-x2 v -x3)
    F = [[1, 2], [-1, 3], [-2, -3]]

    print("! verifier self-test !\n")

    # 1. A correct SAT answer -> should be VERIFIED.
    good = {"result": "SAT", "assignment": {1: True, 2: False, 3: True}}
    print("correct SAT :", verify(F, good)["verdict"])

    # 2. A wrong SAT answer (violates clause [-1,3]: x1=True, x3=False)
    #    -> should be CORRECTNESS_VIOLATION.
    bad = {"result": "SAT", "assignment": {1: True, 2: False, 3: False}}
    out = verify(F, bad)
    print("wrong SAT   :", out["verdict"], "| falsified:", out.get("falsified_clause"))

    # 3. A partial SAT answer (x3 left unset). With x1=True, clause [-1,3] needs
    #    x3=True, so defaulting x3=False should FALSIFY -> CORRECTNESS_VIOLATION.
    #    This demonstrates why a missing variable is dangerous, and why we want
    #    the FPGA to return a full assignment.
    partial = {"result": "SAT", "assignment": {1: True, 2: False}}
    out = verify(F, partial)
    print("partial SAT :", out["verdict"], "| falsified:", out.get("falsified_clause"))

    # 4. An UNSAT formula, FPGA correctly says UNSAT -> VERIFIED via DPLL.
    #    F2 = (x1 v x2)^(-x1 v x2)^(x1 v -x2)^(-x1 v -x2) is unsatisfiable.
    F2 = [[1, 2], [-1, 2], [1, -2], [-1, -2]]
    print("\n(running DPLL cross-check for UNSAT...)")
    print("correct UNSAT:", verify(F2, {"result": "UNSAT"})["verdict"])

    # 5. A wrong UNSAT: FPGA says UNSAT on a satisfiable formula F.
    #    DPLL finds a solution -> CORRECTNESS_VIOLATION with counterexample.
    print("\n(running DPLL cross-check for wrong UNSAT...)")
    out = verify(F, {"result": "UNSAT"})
    print("wrong UNSAT :", out["verdict"], "| counterexample:", out.get("counterexample"))