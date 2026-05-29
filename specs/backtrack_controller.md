# Module Spec: Backtrack Controller

## What it does

After a conflict is analyzed and a backtrack level is chosen, the Backtrack Controller
undoes all variable assignments made after that level. It rewinds the solver state to
the target level, freeing those variables so BCP can re-propagate under the new
learned clause.

Example:
```
Decision stack:
  Level 1: x1 = True
  Level 2: x3 = False (decision), x5 = True (propagated), x7 = False (propagated)
  Level 3: x2 = True (decision), x8 = False (propagated)

Conflict at level 3. Conflict Analyzer says: backtrack to level 1.

Backtrack Controller undoes:
  Level 3: unassign x2, x8
  Level 2: unassign x3, x5, x7

Result: only x1 = True remains. Solver resumes at level 1.
The new learned clause will be unit at level 1, so BCP fires immediately.
```

---

## Role in CDCL

```
CDCL loop:
  1. Unit Propagate → conflict
  2. Conflict Analyze → learned clause + backtrack_level
  3. Backtrack Controller ← this module
     → unassigns all variables above backtrack_level
     → restores assignment/assigned/level/reason arrays
  4. Clause Store adds learned clause
  5. Unit Propagate again (learned clause is now unit)
```

---

## Target scale

| Parameter | Target |
|---|---|
| Max variables | 1024 |
| Max decision levels | 1024 |
| Max assignments to undo | Up to N (full restart in worst case) |

---

## Interface (Amaranth signals)

### Inputs

| Signal | Width | Description |
|---|---|---|
| `start` | 1 | Pulse: begin backtracking |
| `backtrack_level` | 11 | Target level — undo everything strictly above this |
| `assignment[N]` | N | Current assignment values |
| `assigned[N]` | N | Current assigned mask |
| `level[N]` | 11×N | Decision level of each variable |
| `reason[N]` | 15×N | Reason clause of each variable |
| `current_level` | 11 | Current decision level |

### Outputs

| Signal | Width | Description |
|---|---|---|
| `done` | 1 | Pulses when backtrack is complete |
| `assignment_out[N]` | N | Updated values (unchanged at or below target level) |
| `assigned_out[N]` | N | Updated mask (cleared above target level) |
| `level_out[N]` | 11×N | Updated levels (zeroed above target level) |
| `reason_out[N]` | 15×N | Updated reasons (zeroed above target level) |
| `current_level_out` | 11 | New current level = backtrack_level |

---

## Correctness criteria

1. **Complete undo** — every variable with `level[v] > backtrack_level` must have
   `assigned_out[v] = 0`. No variable above the target level may remain assigned.

2. **Preservation** — every variable with `level[v] <= backtrack_level` must keep its
   assignment, level, and reason unchanged. Backtracking must not touch variables
   at or below the target.

3. **Level update** — `current_level_out` must equal `backtrack_level`. The solver
   continues at the target level, not the old level.

4. **Reason preservation** — reason entries for variables at or below `backtrack_level`
   must be unchanged. They are still valid implications at the target level.

5. **Termination** — `done` must pulse within O(N) cycles. The scan over all variables
   is bounded by N.

---

## Performance target

| Metric | Target |
|---|---|
| Clock frequency | ≥ 50 MHz on ECP5-85F |
| Cycles per backtrack | ≤ O(N) |
| LUT budget | ≤ 2000 LUTs |
| FF budget | ≤ 1000 FFs |
| BRAM | 0 |

---

## What a minimal seed looks like

Sequential scan — check every variable, clear those above the target level:

```
for v in 1..num_vars:
    if level[v] > backtrack_level:
        assigned_out[v] = 0
        level_out[v]    = 0
        reason_out[v]   = 0
    else:
        assigned_out[v] = assigned[v]   # unchanged
        level_out[v]    = level[v]
        reason_out[v]   = reason[v]
current_level_out = backtrack_level
```

One variable per cycle. O(N) cycles. Simple and correct.

---

## EVOLVE-BLOCK boundary

The agent may rewrite:
- Parallelism (clear multiple variables per cycle)
- Data structure for tracking which variables belong to which level
- Non-chronological backtracking extensions (already standard CDCL — seed uses it)

The agent may NOT change:
- Signal names and widths in the Interface section
- Correctness criteria 1–5
