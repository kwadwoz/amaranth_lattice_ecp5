# Module Spec: Clause Store

## What it does

The Clause Store is the memory that holds the CNF formula and all learned clauses.
Every other module reads from it — the Unit Propagator scans it looking for unit clauses,
the Conflict Analyzer reads it to perform resolution, and the Decision Heuristic reads
variable activity data derived from it.

There are two kinds of clauses:
- **Original clauses** — loaded once from the input packet, never deleted
- **Learned clauses** — added by the Conflict Analyzer during solving, may be deleted
  to manage memory (clause deletion / garbage collection)

The Clause Store is the largest consumer of block RAM in the design.

---

## Role in CDCL

```
CDCL loop:
  1. Unit Propagate  ← reads Clause Store every cycle
  2. Conflict Analyze ← reads Clause Store to resolve conflicts
  3. Decision Heuristic ← reads activity scores (derived from Clause Store)
  4. Backtrack ← no Clause Store access
```

The Clause Store is accessed more than any other module. Its read latency directly
determines BCP throughput.

---

## Target scale

| Parameter | Target | Notes |
|---|---|---|
| Max original clauses | 10,000 | SATLIB upper bound |
| Max learned clauses | 10,000 | Doubles capacity over original clauses. Subject to deletion. |
| Max literals per clause | 256 | Practical limit. SATLIB 3-SAT uses exactly 3. |
| Max variables | 1024 | 11 bits per literal variable index |
| Literal encoding | 11 bits | 10-bit var index (0-based) + 1-bit sign |
| EBR budget | ≤ 20 EBR blocks | EBR = 18Kb. 20k clauses × 4 literals × 11 bits ≈ 880Kb → ~49 EBR. Budget must be negotiated with Outer Loop. |

---

## Interface (Amaranth signals)

### Clause read port (used by Unit Propagator and Conflict Analyzer)

| Signal | Width | Description |
|---|---|---|
| `read_addr` | 15 | Clause index to read (0-based) |
| `read_en` | 1 | Enable read |
| `read_data` | — | Clause contents: num_literals (8) + literals array |
| `read_valid` | 1 | High when read_data is valid (1-cycle latency for EBR) |

### Clause write port (used by Conflict Analyzer to add learned clauses)

| Signal | Width | Description |
|---|---|---|
| `write_en` | 1 | Write a new learned clause |
| `write_clause` | — | Clause to write: num_literals + literals |
| `write_addr_out` | 15 | Address where clause was stored |
| `write_done` | 1 | Pulses when write is complete |

### Watch literal interface (optional optimization — not required for seed)

| Signal | Width | Description |
|---|---|---|
| `watch_lookup_var` | 11 | Variable to look up watched clauses for |
| `watch_clauses_out` | — | List of clause indices watching this variable |

### Management

| Signal | Width | Description |
|---|---|---|
| `load_start` | 1 | Begin loading original clauses from input buffer |
| `load_done` | 1 | All original clauses loaded |
| `num_original` | 15 | Number of original clauses |
| `num_learned` | 15 | Number of learned clauses currently stored |
| `delete_en` | 1 | Trigger garbage collection of low-activity learned clauses |

---

## Correctness criteria

1. **Read integrity** — reading clause at address A must always return the clause that was
   written to address A. No corruption across reads.

2. **Original clauses immutable** — original clauses (addresses 0 to num_original-1) must
   never be overwritten or deleted.

3. **Learned clause persistence** — a learned clause written at address A must be readable
   at address A until explicitly deleted. A clause that disappears without deletion is a bug.

4. **Deletion safety** — after a learned clause is deleted, its address must not be returned
   by any read used by the solver. Deleted clauses must be marked and skipped.

5. **Capacity reporting** — `num_learned` must accurately reflect the current count of
   active learned clauses. An incorrect count will break garbage collection policy.

---

## Memory layout (EBR)

Each clause occupies a fixed-width row in EBR:

```
Row layout (seed — fixed 4 literals per clause, padded with 0x000 for unused):
  [15:13] unused
  [12:2]  literal_0 (11 bits: 10-bit var index + 1-bit sign)
  [13:3]  literal_1
  [24:14] literal_2
  [35:25] literal_3
  [43:36] num_literals (8 bits — actual count, ignoring padding)
```

A simpler seed layout: each clause spans multiple EBR rows, one literal per row,
with a terminator (0x000) marking end of clause. Easier to implement, wastes
address space, but correct.

---

## Performance target

| Metric | Target |
|---|---|
| Clock frequency | ≥ 50 MHz on ECP5-85F |
| Read latency | 1 cycle (EBR registered read) |
| LUT budget | ≤ 2000 LUTs (mostly routing and control) |
| FF budget | ≤ 1000 FFs |
| BRAM | ≤ 20 EBR blocks |

---

## What a minimal seed looks like

Store all clauses in a flat EBR array, one literal per address, with 0x7FF as
end-of-clause terminator. A separate array stores the start address of each clause.

```
clause_starts[M] = [0, 4, 8, ...]   # where each clause begins
literals[...] = [l0, l1, l2, 0x7FF, l3, l4, l5, 0x7FF, ...]
```

Read interface: given clause index C, look up `clause_starts[C]`, then read
literals sequentially until 0x7FF. Simple, correct, wastes some BRAM.

---

## EVOLVE-BLOCK boundary

The agent may rewrite:
- Memory layout and packing (variable-width vs fixed-width rows)
- Watch literal data structure (two-watched-literals for O(1) propagation)
- Clause activity scoring (for deletion policy)
- Garbage collection strategy (LBD-based vs activity-based)

The agent may NOT change:
- Signal names and widths in the Interface section
- Correctness criteria 1–5
- The constraint that original clauses are never deleted
