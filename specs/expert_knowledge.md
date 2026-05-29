# Expert Knowledge File
# ECP5-85F Hardware Constraints for Amaranth HDL Agent

This file is injected into every openEvolve prompt. It contains platform constraints,
known failure patterns, and Amaranth-specific rules that apply to every module
regardless of what is being built. Read this before generating any candidate.

---

## ECP5-85F Hardware Constraints

### Block RAM (EBR)
- EBR is 18Kb per block with two independent read/write ports
- EBR reads have 1-cycle registered latency — designs assuming combinatorial
  (zero-cycle) reads will fail timing or produce wrong results
- Total EBR on ECP5-85F: 208 blocks (~468 KB total)
- There is NO URAM on ECP5 — any design using URAM primitives will be rejected
  at synthesis. Do not use URAM under any circumstances.
- Large BRAM arrays clustered in one area cause routing congestion in nextpnr.
  Spread EBR usage across the chip using placement constraints where possible.

### LUTs and FFs
- Total LUTs on ECP5-85F: ~85,000
- Total FFs on ECP5-85F: ~85,000
- Target: total composed design must fit within 80% of capacity (~68,000 LUTs)
- Per-module budgets are handed down by the Outer Loop — stay within them

### Clock
- Available clock: 12 MHz from FTDI (pin A10)
- fmax target for composed design: 130 MHz (floor), 150 MHz (stretch goal)
- 230 MHz (SAT-Accel Xilinx figure) is NOT achievable on ECP5 — do not target it
- nextpnr routing congestion becomes the dominant limiter before raw logic timing

### DSP blocks
- ECP5-85F has 156 18x18 multiplier blocks (MULT18X18D)
- Useful for score arithmetic in VSIDS decision heuristic
- Not useful for clause logic or BCP

---

## Amaranth HDL Rules

### Elaboration vs. simulation
- Amaranth elaboration runs Python at elaboration time
- Use `m.If()` / `m.Elif()` / `m.Else()` for hardware conditionals
- Never use Python `if` to branch on signal values — it evaluates at elaboration time,
  not at runtime. This is the most common agent mistake.
- Signal widths must be Python constants at elaboration time, not Amaranth signals

### Signal initialization
- Use `Signal(init=1)` not `Signal(reset=1)` — `reset` is deprecated in Amaranth 0.5+
- Undriven combinatorial signals default to 0 — always explicitly assign in all paths
  to avoid implicit latches

### FSMs
- Use `with m.FSM():` and `with m.State("NAME"):` for state machines
- `m.next = "STATE"` transitions on the next clock edge
- FSM state transitions happen synchronously — plan timing accordingly

### Memory (EBR)
- Use `Memory` from `amaranth.hdl.mem` for block RAM
- Read ports: `memory.read_port(domain="sync")` for registered (1-cycle latency) reads
- Write ports: `memory.write_port()` for synchronous writes
- Registered reads are mandatory for timing closure — transparent reads will fail fmax

### Bit selection
- `signal.bit_select(offset, width)` — selects `width` bits starting at `offset`
- `offset` may be a signal (runtime value)
- `signal[i]` — selects bit i, where i must be a constant

---

## Known Failure Patterns

### Pattern 1: URAM usage
**Symptom:** Synthesis fails with "primitive not found" or similar.
**Cause:** Design references URAM, which does not exist on ECP5.
**Fix:** Replace with EBR (18Kb blocks). Restructure memory access to fit EBR width.

### Pattern 2: Zero-latency EBR read
**Symptom:** SymbiYosys finds counterexample where read data is wrong on first cycle.
**Cause:** Design assumes combinatorial read from EBR, but EBR has 1-cycle latency.
**Fix:** Add a pipeline register to account for the read latency. All reads from EBR
take effect one cycle after the address is presented.

### Pattern 3: Python `if` on signals
**Symptom:** Elaboration error or design behaves identically regardless of input.
**Cause:** `if signal == value:` evaluates at Python elaboration time, not hardware
runtime. The condition is always True or always False.
**Fix:** Replace with `with m.If(signal == value):`.

### Pattern 4: Combinatorial loop
**Symptom:** nextpnr reports combinatorial loop or timing closure fails with negative
slack on a short path.
**Cause:** Output of a module feeds back into its own combinatorial input without a
register in the path.
**Fix:** Break the loop with a registered intermediate signal (`m.d.sync +=`).

### Pattern 5: Unconstrained signal width
**Symptom:** Yosys synthesis produces incorrect resource estimates or SymbiYosys
times out.
**Cause:** Signal declared as `Signal()` (1-bit default) when wider width is needed.
**Fix:** Always specify width explicitly: `Signal(11)` for an 11-bit variable index.

### Pattern 6: Clause width mutation without signature update
**Symptom:** SymbiYosys finds counterexample in propagation after clause width change.
**Cause:** The XOR signature approach in the propagation module assumes a fixed
clause width. If clause width changes, the signature logic must be updated consistently.
**Fix:** Treat clause width and signature width as coupled constants. Change both or
neither.

### Pattern 7: BRAM clustering congestion
**Symptom:** nextpnr fails to close timing above 80 MHz despite simple logic.
**Cause:** Multiple large EBR arrays placed adjacently on the chip, creating routing
congestion.
**Fix:** Use Amaranth placement constraints to distribute EBR blocks. Split large
memories into smaller banks placed in different chip regions.

---

## SymbiYosys Formal Verification Rules

- BMC depth must be set to at least the maximum pipeline depth of the module under
  test, otherwise liveness properties produce spurious counterexamples
- Safety properties (assert statements) are checked by default
- Liveness properties (cover statements) require explicit `mode prove` in the .sby file
- SymbiYosys counterexample traces are the primary debugging artifact — read them
  before generating the next candidate
- A correctness failure requires a fundamentally different fix than a timing failure —
  never treat a SymbiYosys failure as a performance optimization problem

---

## ECP5 fmax Reference

| fmax | Interpretation |
|---|---|
| < 100 MHz | Unacceptable — under-pipelined or congested |
| 100–130 MHz | Minimum viable baseline |
| 130–150 MHz | Target range — use 130 MHz as termination floor |
| 150–175 MHz | Stretch goal — requires aggressive pipelining |
| > 175 MHz | Extremely unlikely for full composed design |

---

## Wire Protocol (frozen — do not modify)

The host-FPGA communication protocol is fixed. All evolved hardware variants must
implement it exactly as specified in `infrastructure/contracts.py`.

- Start marker: `0xAA`
- End marker: `0xFF`
- Clause terminator: `0x00`
- Literal encoding: `(var_index << 1) | sign`, 0-based var index
- Assignment readback: 1 bit per variable, packed LSB-first into bytes, ceil(N/8) bytes
- Result byte: `0x01` = SAT, `0x00` = UNSAT

Agents that change the wire protocol will fail the host-side evaluator with a
CORRECTNESS_VIOLATION even on logically correct designs.
