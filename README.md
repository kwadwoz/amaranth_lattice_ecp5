# Amaranth HDL on Lattice ECP5 Evaluation Board

Hardware design project using [Amaranth HDL](https://amaranth-lang.org/) on the **Lattice LFE5UM5G-85F Evaluation Board** (LFE5UM5G-85F-EVN), building toward an autonomous FPGA SAT solver accelerator driven by an openEvolve-based agentic framework.

---

## Hardware

- **FPGA:** Lattice LFE5UM5G-85F (ECP5-5G, 85K LUT, CABGA381 package)
- **Board:** Lattice ECP5 Evaluation Board (LFE5UM5G-85F-EVN)
- **Clock:** 12 MHz from FTDI U1 (pin A10) — requires USB cable + JP2 in, JP1 out
- **LEDs:** 8 user LEDs D5–D12, active low (pins A13, A12, B19, A18, B18, C17, A17, B17)
- **DIP switches:** SW5, active low (pins J1, H1, K1, E15, D16, B16, C16, A16)

---

## Toolchain

**OSS toolchain (required):**

```bash
# Download OSS CAD Suite (includes yosys, nextpnr-ecp5, ecppack)
curl -L https://github.com/YosysHQ/oss-cad-suite-build/releases/download/2026-05-21/oss-cad-suite-darwin-arm64-20260521.tgz -o ~/oss-cad-suite.tgz
tar -xzf ~/oss-cad-suite.tgz -C ~/
echo 'export PATH="$HOME/oss-cad-suite/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

**Python dependencies:**

```bash
pip install amaranth pyserial
```

**SymbiYosys** (formal verification — included in OSS CAD Suite):
```bash
sby --version   # should print SBY v0.65
```

---

## Files

**Hardware designs:**

| File | Description |
|---|---|
| `traffic_light_ecp5.py` | Traffic light FSM — first hardware design |
| `passthrough_ecp5.py` | Switch → LED passthrough — I/O connectivity test |
| `uart_echo_ecp5.py` | UART echo — receives bytes over serial and sends them back |
| `ecp5-5g-evn.cfg` | OpenOCD config for programming the ECP5-5G EVN board |

**Host scripts:**

| File | Description |
|---|---|
| `hello_fpga.py` | Sends a message over UART and prints the echo |
| `sat_experiment.py` | Sends a DIMACS CNF over UART, prints SAT/UNSAT result |
| `verifier.py`     | Host-side correctness oracle. Checks FPGA SAT/UNSAT answers against the formula |
| `DPLL.py` | DPLL SAT solver in Python (Algorithm 5.1/5.2) — software reference |
| `Tutoroal.py` | Amaranth tutorial exercises — constants, signals, counters, simulation |

**Infrastructure (Phase 0 harness — frozen, not modified by agents):**

| File | Description |
|---|---|
| `infrastructure/contracts.py` | Single source of truth: `Result`, `Status`, `Stats`, `CNF`, wire-format constants |
| `infrastructure/fpga_interface.py` | Abstract base class — defines `build()`, `program()`, `run()`, `solve_sat()` |
| `infrastructure/sim_backend.py` | Pure-software backend — runs solver core in Python, no hardware needed |
| `infrastructure/ecp5_uart_backend.py` | Hardware backend skeleton — `NotImplementedError` stubs with documented intent |
| `infrastructure/stub_core.py` | Brute-force fake solver — exercises the loop end-to-end without real hardware |
| `tests/test_roundtrip.py` | 14 pytest tests proving the full host → backend → core → Result loop works |

---

## Building and Programming

**Build a bitstream:**

```bash
python traffic_light_ecp5.py
# or
python passthrough_ecp5.py
```

Output goes to `build/top.bit` and `build/top.svf`.

**Program the board via JTAG:**

Two USB connections are required:
- **JTAG USB** (FT2232H, connector J32) — for programming
- **CP2102 USB adapter** (connector J39) — for UART communication

```bash
sudo ~/oss-cad-suite/bin/openocd \
  -f /Users/zenasboamah/Amaranth_Tutorial/ecp5-5g-evn.cfg \
  -c "init; svf /Users/zenasboamah/Amaranth_Tutorial/build/top.svf; exit"
```

Use absolute paths with `sudo` — relative paths will fail because sudo runs from a different working directory.

---

## Designs

### Traffic Light FSM (`traffic_light_ecp5.py`)

A finite state machine that cycles through RED → GREEN → YELLOW → RED, spending 1 second in each state. Uses a 12 MHz clock with a 12,000,000-cycle divider to generate the 1 Hz tick.

- LED0 (D5, pin A13) = Red state
- LED1 (D6, pin A12) = Green state
- LED2 (D7, pin B19) = Yellow state

### Switch Passthrough (`passthrough_ecp5.py`)

Wires the DIP switches directly to LEDs with no logic — used to verify pin assignments and I/O connectivity before adding computation.

### UART Echo (`uart_echo_ecp5.py`)

Receives bytes over UART and echoes them back to the host. Uses a software UART implemented in Amaranth with a `UARTReceiver` and `UARTTransmitter` FSM running at 115200 baud on a 12 MHz clock (104 clocks per bit).

**Wiring (J39 header):**

```
CP2102 TXD  →  J39 pin 4  →  FPGA RX (D15)
CP2102 RXD  ←  J39 pin 5  ←  FPGA TX (B15)
CP2102 GND  →  J39 GND
```

**Testing with screen:**

```bash
screen /dev/tty.usbserial-0001 115200
# Type any character — it echoes back
# Exit: Ctrl+A then K then Y
```

**Testing with Python:**

```bash
python hello_fpga.py
# Prints: Received: b'Hello FPGA\r\n'
```

LED 0 (A13) lights while receiving, LED 1 (A12) lights while transmitting.

---

## Project Direction

The goal is an autonomous **CDCL SAT solver accelerator** on the ECP5, driven by an openEvolve-based agentic framework that evolves Amaranth HDL designs and evaluates them through a cascading hardware verification pipeline.

**Architecture (from the design doc):**

```
Outer Loop (Bayesian Optimization)
  └── Inner Loop (openEvolve per module)
        └── Cascading Evaluator (6 stages)
              1. Amaranth elaboration
              2. Amaranth simulation (pytest)
              3. SymbiYosys formal verification  ← sby installed, not yet wired
              4. Yosys resource check vs. budget
              5. Full synthesis
              6. nextpnr place-and-route (fmax target: 130–150 MHz on ECP5)
```

**Agent boundary:** agents modify Amaranth HDL solver kernels only (within `EVOLVE-BLOCK` markers). The host harness (`infrastructure/`) is frozen — agents cannot touch it.

**Fixed host components (from design doc §1.3):**
- **DIMACS Parser** — `read_dimacs()` in `contracts.py`
- **Assignment Verifier** — checks returned assignments satisfy the formula in O(total literals). SAT results → `VERIFIED` or `CORRECTNESS_VIOLATION`. UNSAT results → `NOT_APPLICABLE` with optional DPLL cross-check as temporary safety net until SymbiYosys Stage 3 is wired up.

**Phase status:**
- Phase 0 (Host Harness): complete — `infrastructure/` built, 14 tests passing
- Phase 1 (Seeds): next — per-module spec documents + first valid Amaranth seed per module
- Phase 2+ (Inner Loop, Composition, Outer Loop): future

**Reference:** SAT-Accel (Lo et al., FPGA '25) is the baseline — a CDCL solver on Xilinx UltraScale+. Direct port is not feasible (ECP5 has ~1/3 the LUTs, no URAMs, open-source tooling). The framework evolves new ECP5-native designs from minimal seeds.

---

## Board Notes

- The 200 MHz X2 oscillator (Y19/W20) connects to SERDES PLLs , not usable as a regular IO clock.
- The onboard FTDI UART connection to the FPGA requires 0Ω resistors R34/R35 which are not installed by default. Use a CP2102 adapter on J39 instead.
- Programming uses JTAG via the FTDI FT2232H (Channel A). The device appears as `ECP5 5G EVN` on macOS.
