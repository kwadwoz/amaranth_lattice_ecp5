"""
DPLL satisfiability solver — direct translation of Algorithm 5.1 / 5.2.

Representation (DIMACS-style, the convention every real SAT solver uses):
    Variable x_i      →  positive int  i
    Negative literal  ¬x_i  →  negative int  -i
    Clause            →  list of literals (the OR of those literals)
    Formula F         →  list of clauses (the AND of those clauses)
    Partial assignment m → dict {variable_index: bool}

Example encoding:
    F = (x ∨ y) ∧ (¬x ∨ z) ∧ (¬y ∨ ¬z)   with  x=1, y=2, z=3
    F = [[1, 2], [-1, 3], [-2, -3]]
"""

from typing import Optional


# ---- helpers ---------------------------------------------------------------

def literal_value(lit: int, m: dict[int, bool]) -> Optional[bool]:
    """Truth value of a literal under m, or None if its variable is unassigned."""
    var = abs(lit)
    if var not in m:
        return None
    return m[var] if lit > 0 else not m[var]


def clause_status(clause: list[int], m: dict[int, bool]) -> Optional[bool]:
    """True (satisfied), False (falsified), or None (undetermined)."""
    has_unassigned = False
    for lit in clause:
        v = literal_value(lit, m)
        if v is True:
            return True
        if v is None:
            has_unassigned = True
    return None if has_unassigned else False


def formula_status(F: list[list[int]], m: dict[int, bool]) -> Optional[bool]:
    """True if every clause is True; False if any is False; None otherwise."""
    undetermined = False
    for clause in F:
        s = clause_status(clause, m)
        if s is False:
            return False
        if s is None:
            undetermined = True
    return None if undetermined else True


def find_unit_literal(F: list[list[int]], m: dict[int, bool]) -> Optional[int]:
    """Return a unit literal if one exists, else None.

    A clause has a unit literal when it is undetermined and exactly one of its
    literals is unassigned (the rest must therefore all be False)."""
    for clause in F:
        if clause_status(clause, m) is not None:
            continue
        unassigned = [lit for lit in clause if literal_value(lit, m) is None]
        if len(unassigned) == 1:
            return unassigned[0]
    return None


def fmt(m: dict[int, bool]) -> str:
    if not m:
        return "{}"
    return "{" + ", ".join(f"x{v}={int(b)}" for v, b in sorted(m.items())) + "}"


# ---- DPLL ------------------------------------------------------------------

def dpll(F: list[list[int]],
         m: Optional[dict[int, bool]] = None,
         depth: int = 0) -> tuple[str, Optional[dict[int, bool]]]:
    """Algorithm 5.2. Returns ('sat', witness) or ('unsat', None)."""
    if m is None:
        m = {}
    pad = "  " * depth

    # base cases
    status = formula_status(F, m)
    if status is True:
        print(f"{pad}sat  at {fmt(m)}")
        return ("sat", m)
    if status is False:
        print(f"{pad}unsat at {fmt(m)}")
        return ("unsat", None)

    # unit propagation (forced moves)
    unit = find_unit_literal(F, m)
    if unit is not None:
        var, val = abs(unit), unit > 0
        print(f"{pad}propagate x{var} -> {int(val)}  (unit literal {unit:+d})")
        return dpll(F, {**m, var: val}, depth + 1)

    # decision: pick smallest unassigned variable, try True before False
    all_vars = {abs(lit) for clause in F for lit in clause}
    p = min(all_vars - set(m.keys()))

    for b in (True, False):
        print(f"{pad}decide   x{p} -> {int(b)}")
        result, witness = dpll(F, {**m, p: b}, depth + 1)
        if result == "sat":
            return ("sat", witness)
        print(f"{pad}backtrack from x{p} -> {int(b)}")

    return ("unsat", None)


# ---- examples --------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Example 1 (SAT):  F = (x ∨ y) ∧ (¬x ∨ z) ∧ (¬y ∨ ¬z)")
    print("                 encoding x=1, y=2, z=3")
    print("=" * 60)
    F1 = [[1, 2], [-1, 3], [-2, -3]]
    result, witness = dpll(F1)
    print(f"\nResult: {result}")
    if witness:
        print(f"Witness: {fmt(witness)}")

    print("\n" + "=" * 60)
    print("Example 2 (UNSAT, shows backtracking):")
    print("  F = (x ∨ y) ∧ (¬x ∨ y) ∧ (x ∨ ¬y) ∧ (¬x ∨ ¬y)")
    print("=" * 60)
    F2 = [[1, 2], [-1, 2], [1, -2], [-1, -2]]
    result, witness = dpll(F2)
    print(f"\nResult: {result}")