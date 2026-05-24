# passthrough_ecp5.py
# Read 8 DIP switches, display value on 8 LEDs.
# Flip switch N ON -> LED N lights up. No logic in between.
#
# Board setup:
#   USB cable to J2, JP2 installed, JP1 removed, 12 V to J37
#
# Build:   python passthrough_ecp5.py
# Program: sudo ~/oss-cad-suite/bin/openocd \
#            -f /Users/zenasboamah/Amaranth_Tutorial/ecp5-5g-evn.cfg \
#            -c "init; svf build/top.svf; exit"

from amaranth import *
from amaranth.vendor import LatticeECP5Platform
from amaranth.build import Resource, Subsignal, Pins, PinsN, Clock, Attrs


class ECP5EVNPlatform(LatticeECP5Platform):
    device      = "LFE5UM5G-85F"
    package     = "BG381"
    speed       = "8"
    default_clk = "clk12"

    resources = [
        Resource("clk12", 0,
            Pins("A10", dir="i"),
            Clock(12e6),
            Attrs(IO_TYPE="LVCMOS33"),
        ),
        # LEDs D5-D12, active low (Table 7.4)
        Resource("led", 0, PinsN("A13", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
        Resource("led", 1, PinsN("A12", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
        Resource("led", 2, PinsN("B19", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
        Resource("led", 3, PinsN("A18", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
        Resource("led", 4, PinsN("B18", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
        Resource("led", 5, PinsN("C17", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
        Resource("led", 6, PinsN("A17", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
        Resource("led", 7, PinsN("B17", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
        # DIP switches SW5 positions 1-8, active low (Table 7.1)
        Resource("sw", 0, PinsN("J1",  dir="i"), Attrs(IO_TYPE="LVCMOS33")),
        Resource("sw", 1, PinsN("H1",  dir="i"), Attrs(IO_TYPE="LVCMOS33")),
        Resource("sw", 2, PinsN("K1",  dir="i"), Attrs(IO_TYPE="LVCMOS33")),
        # UART through CP2102 on J39:
        #   CP2102 TXD -> J39 pin 4  -> FPGA RX (D15)
        #   CP2102 RXD <- J39 pin 5  <- FPGA TX (B15)
        #   CP2102 GND -> J39 GND
        Resource("uart", 0,
            Subsignal("rx", Pins("D15", dir="i")),
            Subsignal("tx", Pins("B15", dir="o")),
            Attrs(IO_TYPE="LVCMOS33"),
        ),

    ]

    connectors = []


class Top(Elaboratable):
    def elaborate(self, platform):
        m = Module()

        # Wire the 3 switches to the first 3 LEDs
        for i in range(3):
            sw  = platform.request("sw",  i)
            led = platform.request("led", i)
            m.d.comb += led.o.eq(sw.i)

        # Turn off the remaining 5 LEDs
        for i in range(3, 8):
            led = platform.request("led", i)
            m.d.comb += led.o.eq(0)

        return m


if __name__ == "__main__":
    ECP5EVNPlatform().build(Top(), do_program=False)
