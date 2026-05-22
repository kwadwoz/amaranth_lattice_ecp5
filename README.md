# Amaranth HDL on Lattice ECP5 Evaluation Board

Learning project exploring hardware design with [Amaranth HDL](https://amaranth-lang.org/) on the **Lattice LFE5UM5G-85F Evaluation Board** (LFE5UM5G-85F-EVN), working toward a CDCL SAT solver accelerator.

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
pip install amaranth
```

---

## Files

| File | Description |
|---|---|
| `Tutoroal.py` | Amaranth tutorial exercises — constants, signals, counters, simulation |
| `DPLL.py` | DPLL SAT solver in Python (Algorithm 5.1/5.2) — software reference |
| `traffic_light_ecp5.py` | Traffic light FSM on the FPGA — first hardware design |
| `passthrough_ecp5.py` | Switch → LED passthrough — I/O connectivity test |
| `ecp5-5g-evn.cfg` | OpenOCD config for programming the ECP5-5G EVN board |

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

```bash
sudo ~/oss-cad-suite/bin/openocd \
  -f ecp5-5g-evn.cfg \
  -c "init; svf build/top.svf; exit"
```

---

## Designs

### Traffic Light FSM (`traffic_light_ecp5.py`)

A finite state machine that cycles through RED → GREEN → YELLOW → RED, spending 1 second in each state. Uses a 12 MHz clock with a 12,000,000-cycle divider to generate the 1 Hz tick.

- LED0 (D5, pin A13) = Red state
- LED1 (D6, pin A12) = Green state
- LED2 (D7, pin B19) = Yellow state

### Switch Passthrough (`passthrough_ecp5.py`)

Wires the DIP switches directly to LEDs with no logic — used to verify pin assignments and I/O connectivity before adding computation.

---

## Project Direction

The end goal is a **CDCL (Conflict-Driven Clause Learning) SAT solver accelerator** on the ECP5 FPGA. CDCL extends DPLL with clause learning and non-chronological backtracking — the algorithm used by all modern SAT solvers (MiniSAT, Z3, CaDiCaL).

The software DPLL implementation in `DPLL.py` serves as a functional reference for the hardware design.

A UART interface (via CP2102 USB adapter on GPIO header J8) will be used to stream CNF formulas to the FPGA and receive satisfying assignments back to the host.

---

## Board Notes

- The 200 MHz X2 oscillator (Y19/W20) connects to SERDES PLLs , not usable as a regular IO clock.
- The onboard FTDI UART connection to the FPGA requires 0Ω resistors R34/R35 which are not installed by default. Use a CP2102 adapter on J8 instead.
- Programming uses JTAG via the FTDI FT2232H (Channel A). The device appears as `ECP5 5G EVN` on macOS.
