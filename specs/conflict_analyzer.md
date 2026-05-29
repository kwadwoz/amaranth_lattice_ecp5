# Module Spec: Conflict Analyzer

## What it does

When the Unit Propagator finds a conflict (a clause where every literal is false), the
solver cannot continue — it has reached a contradiction. The Conflict Analyzer figures
out **why** the conflict happened and produces a **learned clause** that prevents the
same contradiction from recurring.

This is done via **resolution**: tracing back through the implication graph to find the
smallest set of decisions that caused the conflict, then encoding that set as a new clause.

Example:
```
Decision: x1 = True (level 2)
Propagation: x1=True forced x3=False (clause: ¬x1 ∨ ¬x3)
Propagation: x3=False forced x5=True (clause: x3 ∨ x5)
Conflict: clause (¬x5 ∨ ¬x2) is false under x5=True, x2=True

Conflict Analyzer traces back:
  Why is x5=True? Because x3=False. Why x3=False? Because x1=True (decision).
  Learned clause: (¬x1 ∨ ¬x2) — if x1=True AND x2=True, conflict is inevitable.
  Backtrack to level 1 (second-highest level in learned clause).
```

The learned clause is added to the Clause Store and will be used by BCP going forward,
making future searches smarter.

---

## Role in CDCL

```
CDCL loop:
  1. Unit Propagate → finds conflict
  2. Conflict Analyzer ← this module
     → produces learned clause + backtrack level
  3. Backtrack Controller uses backtrack level
  4. Learned clause added to Clause Store
  5. Decision Heuristic bumps scores for variables in learned clause
  → go to 1
```

---

## Target scale

| Parameter | Target | Notes |
|---|---|---|
| Max variables | 1024 | |
| Max decision levels | 1024 | One per variable in the worst case |
| Max learned clause width | 256 literals | Practical limit — most learned clauses are short |
| Implication graph depth | ≤ N | Bounded by number of variables |

---

## Interface (Amaranth signals)

### Inputs

| Signal | Width | Description |
|---|---|---|
| `start` | 1 | Pulse: begin conflict analysis |
| `conflict_clause` | 15 | Index of the conflicting clause in Clause Store |
| `assignment[N]` | N | Current full assignment (values) |
| `assigned[N]` | N | Which variables are assigned |
| `reason[N]` | 15×N | For each variable, the clause index that forced it (0 = decision) |
| `level[N]` | 11×N | Decision level at which each variable was assigned |
| `current_level` | 11 | Current decision level |

### Outputs

| Signal | Width | Description |
|---|---|---|
| `done` | 1 | Pulses when analysis is complete |
| `learned_lits` | — | Literals of the learned clause (variable-length) |
| `learned_len` | 8 | Number of literals in the learned clause |
| `backtrack_level` | 11 | Level to backtrack to (second-highest level in learned clause) |
| `bump_vars[N]` | N | Bitmask of variables in learned clause — sent to Decision Heuristic |

---

## Correctness criteria

1. **1-UIP property** — the learned clause must contain exactly one literal from the
   current decision level. This is the standard CDCL guarantee. A seed may use a
   simpler cut (e.g. decision-level cut); the agent should converge toward 1-UIP.

2. **Backtrack level correctness** — `backtrack_level` must be the second-highest
   decision level among all literals in the learned clause. Backtracking too far loses
   information; not far enough causes an infinite loop.

3. **Learned clause validity** — every literal in `learned_lits` must be falsified under
   the current assignment. A learned clause with a true literal is useless and wastes
   Clause Store space.

4. **Termination** — `done` must pulse within a bounded number of cycles. The
   resolution procedure terminates because the implication graph is acyclic.

5. **No mutation of inputs** — the Conflict Analyzer is read-only with respect to the
   assignment, reason, and level arrays. It must not modify these.

---

## Implication graph

The implication graph is the data structure BCP maintains as it propagates:
- Each propagated variable has a **reason** (the clause that forced it) and a **level**
  (the decision level when it was assigned)
- Decision variables have reason = 0 (no clause forced them)
- The Conflict Analyzer traverses this graph backwards from the conflict

For the seed, this graph is stored as two arrays:
```
reason[var] = clause index that forced var (0 if decision variable)
level[var]  = decision level when var was assigned
```

---

## Performance target

| Metric | Target |
|---|---|
| Clock frequency | ≥ 50 MHz on ECP5-85F |
| Cycles per analysis | ≤ O(N) |
| LUT budget | ≤ 4000 LUTs |
| FF budget | ≤ 2000 FFs |
| BRAM | 0–2 EBR blocks |

---

## What a minimal seed looks like

Sequential resolution scan:

```
Initialize learned = literals of conflict_clause
while more than one literal in learned is at current_level:
    pick any literal L at current_level
    replace L with the literals of reason[var(L)] not already in learned
learned clause = result
backtrack_level = second-highest level in learned
```

One resolution step per cycle. O(N) per conflict. Correct, not fast.
The agent optimizes pipelining and parallelism from this base.

---

## EVOLVE-BLOCK boundary

The agent may rewrite:
- Resolution order and traversal strategy
- Cut selection (1-UIP vs. all-UIP vs. decision-level cut)
- Pipelining of the resolution loop
- Minimization of learned clause (removing redundant literals)

The agent may NOT change:
- Signal names and widths in the Interface section
- Correctness criteria 2–5 (criterion 1 is a quality target, not a hard gate for the seed)
- The constraint that learned clauses are written to the Clause Store
