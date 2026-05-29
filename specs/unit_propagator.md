# Module Spec: Unit Propagator

## What it does

Unit propagation is the core engine of CDCL. When a clause has all its literals
false except one, that last literal is **forced** — it must be true or the
formula is immediately unsatisfied. The unit propagator finds and applies all
such forced assignments repeatedly until nothing more can be forced, or a
conflict is found.

Example:
```
Clause: (¬x1 ∨ x3)
Current assignment: x1 = True

x1 is True, so ¬x1 is False.
The only literal left is x3 — it must be True.
→ Force x3 = True.
```

This is called **Boolean Constraint Propagation (BCP)**.

---

## Role in CDCL

```
CDCL loop:
  1. Unit Propagate   ← this module
  2. If conflict → Conflict Analyze → Backtrack
  3. If all variables assigned → SAT
  4. Decision Heuristic → pick next variable → go to 1
```

The unit propagator runs after every decision and after every backtrack.
It must be fast — BCP accounts for ~80–90% of solver runtime.

---

## Target scale

| Parameter | Target | Notes |
|---|---|---|
| Max variables (N) | 1024 | SATLIB instances have <1k variables. Wire format needs 2-byte var count — current `contracts.py` uses 1 byte (max 255). Needs resolving with Andrew before hardware is wired. |
| Max clauses (M) | 10,000 | SATLIB instances have up to ~10k clauses. Wire format needs 2-byte clause count. Same open question. |
| Max literals per clause | 3–4 | SATLIB is uniform random 3-SAT. Seed may assume 3 literals per clause; agent may generalize. |
| Clause store size | ≤ 2 EBR blocks | EBR is 18Kb per block, two ports. 10k clauses × 4 literals × 11 bits/literal ≈ 440Kb → ~25 EBR blocks. Budget must be negotiated with Outer Loop. |

---

## Interface (Amaranth signals)

### Inputs

| Signal | Width | Description |
|---|---|---|
| `start` | 1 | Pulse high for one cycle to begin propagation |
| `assignment[N]` | N | Current partial assignment, one bit per variable |
| `assigned[N]` | N | Which variables have been assigned (1 = assigned) |
| `clause_db` | — | Clause database (stored in block RAM, addressed externally) |
| `num_vars` | 8 | Number of variables in the formula |
| `num_clauses` | 8 | Number of clauses in the formula |

### Outputs

| Signal | Width | Description |
|---|---|---|
| `done` | 1 | Pulses high when propagation is complete |
| `conflict` | 1 | High when a conflict was found (held until `start` again) |
| `conflict_clause` | 8 | Index of the clause that caused the conflict |
| `forced_var` | 8 | Most recently forced variable index (1-based) |
| `forced_val` | 1 | Value the variable was forced to |
| `forced_valid` | 1 | Pulses high when a new forced assignment is produced |
| `assignment_out[N]` | N | Updated assignment after propagation |
| `assigned_out[N]` | N | Updated assigned mask after propagation |

---

## Correctness criteria

A correct unit propagator must satisfy all of the following:

1. **Completeness** — if any clause is unit under the current assignment, the
   propagator must find and force it. It must not stop early.

2. **No false conflicts** — `conflict` must only go high if a clause has every
   literal false under the current assignment. It must never fire on a
   satisfiable formula with no real conflict.

3. **No missed conflicts** — if a clause is empty (all literals false),
   `conflict` must go high. The solver cannot continue past a real conflict.

4. **Termination** — the propagator must always reach `done` in finite cycles.
   It must not loop forever on any valid input.

5. **Assignment consistency** — every variable in `assigned_out` that was also
   in `assigned` (input) must keep the same value in `assignment_out`.
   Propagation never overwrites a previously decided variable.

---

## Clause database layout (block RAM)

Each clause is stored as a row of literals. Literals use the encoding from
`contracts.py`:

```
literal byte = (var_index << 1) | sign
  var_index: 0-based  (DIMACS var 1 → index 0)
  sign: 0 = positive, 1 = negated
  0x00 = end of clause
```

Example — clause `(¬x1 ∨ x3)` in DIMACS = `(-1, 3)`:
```
byte 0: (0 << 1) | 1 = 0x01   ← ¬x1
byte 1: (2 << 1) | 0 = 0x04   ← x3
byte 2: 0x00                   ← end of clause
```

---

## Performance target

| Metric | Target |
|---|---|
| Clock frequency | ≥ 50 MHz on ECP5-85F (stretch: 100 MHz) |
| Cycles per propagation | ≤ O(N × M) worst case |
| LUT budget | ≤ 8000 LUTs (set conservatively — exact budget handed down by Outer Loop) |
| FF budget | ≤ 4000 FFs |
| BRAM | ≤ 6 EBR blocks for clause storage |
| SATLIB solve time | All uniform random 3-SAT instances (<1k vars, <10k clauses) within 30s on hardware |

---

## What a minimal seed looks like

A correct seed does not need to be fast. It just needs to be right.
The simplest correct implementation:

```
for each clause:
    count unassigned literals
    count false literals
    if false_count == len(clause):
        → conflict
    if false_count == len(clause) - 1 and unassigned_count == 1:
        → force the unassigned literal
repeat until no new assignments are made
```

This is O(N × M) per round and may take multiple rounds. That is acceptable
for a seed — the agent can optimize later.

---

## EVOLVE-BLOCK boundary

The agent may rewrite everything between the EVOLVE-BLOCK markers:
- The internal FSM and datapath
- How the clause database is traversed
- Pipelining and parallelism
- Watch literal optimization (two-watched-literals scheme)

The agent may NOT change:
- The signal names and widths listed in the Interface section above
- The clause database encoding
- The correctness criteria
