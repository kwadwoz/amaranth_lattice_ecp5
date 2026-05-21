# Traffic Light FSM for Lattice ECP5 Evaluation Board (LFE5UM5G-85F-EVN)
#
# Board setup:
#   - USB cable connected to J2 (provides the 12 MHz clock from FTDI U1)
#   - JP2 installed, JP1 removed  (routes 12 MHz clock to FPGA pin A10)
#   - Power via J37 (12 V DC)
#
# Note: The 200 MHz X2 oscillator (Y19/W20) feeds the SERDES PLLs and is not
#       accessible as a regular IO pin, so the 12 MHz USB clock is used instead.
#
# Toolchain required (OSS):
#   yosys, nextpnr-ecp5, ecppack  (Project Trellis)
#
# Build:
#   python traffic_light_ecp5.py          -> writes build/ directory
#
# Program (after build):
#   openocd -f interface/ftdi/lattice_ecp5_evb.cfg \
#           -f target/lattice_ecp5.cfg \
#           -c "svf build/top.svf; exit"
#
# LEDs used:
#   LED0 (A13) = Red
#   LED1 (A12) = Green
#   LED2 (B19) = Yellow
#
# Each state lasts 1 second.  RED -> GREEN -> YELLOW -> RED ...

from amaranth import *
from amaranth.vendor import LatticeECP5Platform
from amaranth.build import Resource, Pins, PinsN, Clock, Attrs



# Platform


class ECP5EVNPlatform(LatticeECP5Platform):
    """Lattice ECP5 Evaluation Board — LFE5UM5G-85F-EVN."""
    device      = "LFE5UM5G-85F"
    package     = "BG381"
    speed       = "8"
    default_clk = "clk12"

    resources = [
        # 12 MHz clock from FTDI U1 (Table 4.1). Requires USB cable + JP2 in, JP1 out.
        Resource("clk12", 0,
            Pins("A10", dir="i"),
            Clock(12e6),
            Attrs(IO_TYPE="LVCMOS33"),
        ),
        # 8 user LEDs, Bank 1, active low (Table 7.4, User Guide)
        Resource("led", 0, PinsN("A13", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
        Resource("led", 1, PinsN("A12", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
        Resource("led", 2, PinsN("B19", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
        Resource("led", 3, PinsN("A18", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
        Resource("led", 4, PinsN("B18", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
        Resource("led", 5, PinsN("C17", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
        Resource("led", 6, PinsN("A17", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
        Resource("led", 7, PinsN("B17", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
        # Generic push button SW4 (Table 7.3, User Guide), active low
        Resource("button", 0, PinsN("P4", dir="i"), Attrs(IO_TYPE="LVCMOS33")),
    ]

    connectors = []



# 1 Hz tick generator


class TickGen(Elaboratable):
    """Pulses tick high for one clock cycle every second (12 MHz input)."""

    CLK_FREQ = 12_000_000

    def __init__(self):
        self.tick = Signal()

    def elaborate(self, platform):
        m = Module()
        counter = Signal(range(self.CLK_FREQ))
        m.d.sync += self.tick.eq(0)
        with m.If(counter == self.CLK_FREQ - 1):
            m.d.sync += counter.eq(0)
            m.d.sync += self.tick.eq(1)
        with m.Else():
            m.d.sync += counter.eq(counter + 1)
        return m


# Traffic light FSM  (bugs from Tutoroal.py corrected)


class TrafficLight(Elaboratable):
    def __init__(self):
        self.tick   = Signal()
        self.red    = Signal()
        self.green  = Signal()
        self.yellow = Signal()

    def elaborate(self, platform):
        m = Module()
        with m.FSM():
            with m.State("RED"):
                m.d.comb += self.red.eq(1)
                with m.If(self.tick):
                    m.next = "GREEN"
            with m.State("GREEN"):
                m.d.comb += self.green.eq(1)
                with m.If(self.tick):
                    m.next = "YELLOW"
            with m.State("YELLOW"):
                m.d.comb += self.yellow.eq(1)      # was wrongly self.green
                with m.If(self.tick):
                    m.next = "RED"
        return m



# Top-level: wire everything to physical pins


class Top(Elaboratable):
    def elaborate(self, platform):
        m = Module()

        tick_gen = TickGen()
        traffic  = TrafficLight()

        m.submodules.tick_gen = tick_gen
        m.submodules.traffic  = traffic

        m.d.comb += traffic.tick.eq(tick_gen.tick)

        led_red    = platform.request("led", 0)   # LED0 → Red
        led_green  = platform.request("led", 1)   # LED1 → Green
        led_yellow = platform.request("led", 2)   # LED2 → Yellow

        m.d.comb += [
            led_red.o.eq(traffic.red),
            led_green.o.eq(traffic.green),
            led_yellow.o.eq(traffic.yellow),
        ]

        return m



# Build entry point


if __name__ == "__main__":
    ECP5EVNPlatform().build(Top(), do_program=False)
