# Module Spec: Decision Heuristic (VSIDS)

## What it does

When no clause can force a variable assignment (nothing left to propagate), the solver
must pick a variable to try next. This is the decision. The Decision Heuristic scores every
unassigned variable and picks the one with the highest score.

The standard heuristic is **VSIDS (Variable State Independent Decaying Sum)**:
- Every variable starts with a score of 0
- When a conflict occurs, every variable involved in that conflict gets its score bumped up
- All scores are periodically decayed (multiplied by a factor < 1) so recent conflicts
  matter more than old ones
- Always pick the unassigned variable with the highest score

Example:
```
Conflict involved x3, x7, x12 → bump their scores
All scores × 0.95  (decay)
Next decision: pick highest-scored unassigned variable → x7
```

VSIDS is why modern CDCL solvers are fast — variables that caused recent conflicts are
likely to cause future conflicts, so trying them first prunes the search tree.

---

## Role in CDCL

```
CDCL loop:
  1. Unit Propagate
  2. If conflict → Conflict Analyze → Backtrack
  3. If all variables assigned → SAT
  4. Decision Heuristic → pick next variable  ← this module
     → assign it → go to 1
```

The decision heuristic runs once per decision level. It is not on the critical timing path
of BCP — correctness matters more than speed here.

---

## Target scale

| Parameter | Target | Notes |
|---|---|---|
| Max variables (N) | 1024 | SATLIB instances. Must track one score per variable. |
| Score width | 16–32 bits | Fixed-point. Agent may choose width. |
| Decay period | Every K conflicts | K is a tunable parameter (typical: K=1, decay on every conflict) |
| Decay factor | ~0.95 | Multiply all scores by 0.95 after each conflict. Implemented as a right-shift approximation. |

---

## Interface (Amaranth signals)

### Inputs

| Signal | Width | Description |
|---|---|---|
| `bump` | 1 | Pulse: bump scores for variables in `bump_vars` |
| `bump_vars[N]` | N | Bitmask — which variables to bump (set on conflict) |
| `decay` | 1 | Pulse: apply decay to all scores |
| `assigned[N]` | N | Which variables are currently assigned (skip these) |
| `num_vars` | 11 | Number of variables in the formula (up to 1024) |
| `request` | 1 | Pulse: request the next decision variable |

### Outputs

| Signal | Width | Description |
|---|---|---|
| `decision_var` | 11 | Index of chosen variable (1-based) |
| `decision_val` | 1 | Value to assign (0 or 1 — always try True first in seed) |
| `decision_valid` | 1 | Pulses high when `decision_var` / `decision_val` are ready |
| `all_assigned` | 1 | High if every variable is already assigned (formula is SAT) |

---

## Correctness criteria

1. **No assigned variable chosen** — `decision_var` must always index a variable where
   `assigned[decision_var - 1] == 0`. The solver cannot re-decide an already-set variable.

2. **Valid index** — `decision_var` must be in [1, num_vars]. Never 0, never out of range.

3. **all_assigned accuracy** — `all_assigned` must go high if and only if every variable
   in [1, num_vars] is in `assigned`. A false `all_assigned` causes the solver to declare
   SAT prematurely — this is a correctness bug.

4. **Termination** — `decision_valid` must pulse within a bounded number of cycles after
   `request`. The module must not stall indefinitely searching for an unassigned variable.

5. **Score integrity after backtrack** — scores must not be reset on backtrack. VSIDS
   scores are persistent across the entire solve — they accumulate evidence over the
   lifetime of the run.

---

## Performance target

| Metric | Target |
|---|---|
| Clock frequency | ≥ 50 MHz on ECP5-85F |
| Cycles to decision | ≤ N cycles (linear scan is acceptable for seed) |
| LUT budget | ≤ 3000 LUTs |
| FF budget | ≤ 2000 FFs |
| BRAM | 0–1 EBR blocks (score table may fit in registers for small N) |

---

## What a minimal seed looks like

A correct seed does not need VSIDS. The simplest correct implementation:

```
scan variables 1..N in order
return the first unassigned variable, assign it True
```

This is just "first unassigned" — O(N) scan, no scoring, always assigns True.
It is correct but produces terrible solve performance. The agent optimizes from here.

A step up — static VSIDS (no decay, just bump on conflict):
```
scores[N] = all zeros
on bump(vars): for each v in vars: scores[v] += 1
on request: return argmax(scores) among unassigned vars
```

---

## EVOLVE-BLOCK boundary

The agent may rewrite everything between the EVOLVE-BLOCK markers:
- Score representation (fixed-point width, scaling)
- Decay implementation (shift approximation, decay period)
- Search strategy (linear scan → priority queue → parallel argmax)
- Polarity heuristic (always True → phase saving → random)

The agent may NOT change:
- Signal names and widths listed in the Interface section
- Correctness criteria 1–5
