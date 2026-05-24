# UART echo test for Lattice ECP5 Evaluation Board (LFE5UM5G-85F-EVN)
#
# Connect a 3.3 V USB-UART adapter to J39:
#   CP2102 TXD -> J39 pin 4  -> FPGA RX (D15)
#   CP2102 RXD <- J39 pin 5  <- FPGA TX (B15)
#   CP2102 GND -> J39 GND
#
# Serial settings: 115200 baud, 8 data bits, no parity, 1 stop bit.
#
# Build:   python uart_echo_ecp5.py
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
        Resource("led", 0, PinsN("A13", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
        Resource("led", 1, PinsN("A12", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
        Resource("led", 2, PinsN("B19", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
        Resource("led", 3, PinsN("A18", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
        Resource("led", 4, PinsN("B18", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
        Resource("led", 5, PinsN("C17", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
        Resource("led", 6, PinsN("A17", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
        Resource("led", 7, PinsN("B17", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
        Resource("uart", 0,
            Subsignal("rx", Pins("D15", dir="i")),
            Subsignal("tx", Pins("B15", dir="o")),
            Attrs(IO_TYPE="LVCMOS33"),
        ),
    ]

    connectors = []


class UARTReceiver(Elaboratable):
    def __init__(self, clocks_per_bit):
        self.rx = Signal(reset=1)
        self.data = Signal(8)
        self.valid = Signal()
        self.busy = Signal()
        self.clocks_per_bit = clocks_per_bit

    def elaborate(self, platform):
        m = Module()

        bit_timer = Signal(range(self.clocks_per_bit))
        bit_index = Signal(range(8))
        shift = Signal(8)

        m.d.sync += self.valid.eq(0)

        with m.FSM():
            with m.State("IDLE"):
                m.d.sync += self.busy.eq(0)
                with m.If(~self.rx):
                    m.d.sync += [
                        self.busy.eq(1),
                        bit_timer.eq(self.clocks_per_bit // 2),
                    ]
                    m.next = "START"

            with m.State("START"):
                with m.If(bit_timer == 0):
                    with m.If(~self.rx):
                        m.d.sync += [
                            bit_timer.eq(self.clocks_per_bit - 1),
                            bit_index.eq(0),
                        ]
                        m.next = "DATA"
                    with m.Else():
                        m.next = "IDLE"
                with m.Else():
                    m.d.sync += bit_timer.eq(bit_timer - 1)

            with m.State("DATA"):
                with m.If(bit_timer == 0):
                    m.d.sync += [
                        shift.bit_select(bit_index, 1).eq(self.rx),
                        bit_timer.eq(self.clocks_per_bit - 1),
                    ]
                    with m.If(bit_index == 7):
                        m.next = "STOP"
                    with m.Else():
                        m.d.sync += bit_index.eq(bit_index + 1)
                with m.Else():
                    m.d.sync += bit_timer.eq(bit_timer - 1)

            with m.State("STOP"):
                with m.If(bit_timer == 0):
                    m.d.sync += [
                        self.data.eq(shift),
                        self.valid.eq(self.rx),
                    ]
                    m.next = "IDLE"
                with m.Else():
                    m.d.sync += bit_timer.eq(bit_timer - 1)

        return m


class UARTTransmitter(Elaboratable):
    def __init__(self, clocks_per_bit):
        self.tx = Signal(reset=1)
        self.data = Signal(8)
        self.start = Signal()
        self.busy = Signal()
        self.clocks_per_bit = clocks_per_bit

    def elaborate(self, platform):
        m = Module()

        bit_timer = Signal(range(self.clocks_per_bit))
        bit_index = Signal(range(8))
        shift = Signal(8)

        with m.FSM():
            with m.State("IDLE"):
                m.d.sync += [
                    self.tx.eq(1),
                    self.busy.eq(0),
                ]
                with m.If(self.start):
                    m.d.sync += [
                        self.busy.eq(1),
                        self.tx.eq(0),
                        shift.eq(self.data),
                        bit_timer.eq(self.clocks_per_bit - 1),
                        bit_index.eq(0),
                    ]
                    m.next = "START"

            with m.State("START"):
                with m.If(bit_timer == 0):
                    m.d.sync += [
                        self.tx.eq(shift[0]),
                        bit_timer.eq(self.clocks_per_bit - 1),
                    ]
                    m.next = "DATA"
                with m.Else():
                    m.d.sync += bit_timer.eq(bit_timer - 1)

            with m.State("DATA"):
                with m.If(bit_timer == 0):
                    with m.If(bit_index == 7):
                        m.d.sync += [
                            self.tx.eq(1),
                            bit_timer.eq(self.clocks_per_bit - 1),
                        ]
                        m.next = "STOP"
                    with m.Else():
                        m.d.sync += [
                            bit_index.eq(bit_index + 1),
                            self.tx.eq(shift.bit_select(bit_index + 1, 1)),
                            bit_timer.eq(self.clocks_per_bit - 1),
                        ]
                with m.Else():
                    m.d.sync += bit_timer.eq(bit_timer - 1)

            with m.State("STOP"):
                with m.If(bit_timer == 0):
                    m.next = "IDLE"
                with m.Else():
                    m.d.sync += bit_timer.eq(bit_timer - 1)

        return m


class Top(Elaboratable):
    CLK_FREQ = 12_000_000
    BAUD = 115_200
    CLKS_PER_BIT = round(CLK_FREQ / BAUD)

    def elaborate(self, platform):
        m = Module()

        uart_pins = platform.request("uart", 0)
        led_rx = platform.request("led", 0)
        led_tx = platform.request("led", 1)

        rx = UARTReceiver(self.CLKS_PER_BIT)
        tx = UARTTransmitter(self.CLKS_PER_BIT)
        m.submodules.rx = rx
        m.submodules.tx = tx

        pending = Signal()
        pending_data = Signal(8)

        m.d.comb += [
            rx.rx.eq(uart_pins.rx.i),
            uart_pins.tx.o.eq(tx.tx),
            tx.data.eq(pending_data),
            tx.start.eq(pending & ~tx.busy),
            led_rx.o.eq(rx.busy),
            led_tx.o.eq(tx.busy),
        ]

        with m.If(rx.valid):
            m.d.sync += [
                pending.eq(1),
                pending_data.eq(rx.data),
            ]
        with m.Elif(tx.start):
            m.d.sync += pending.eq(0)

        return m


if __name__ == "__main__":
    ECP5EVNPlatform().build(Top(), do_program=False)
