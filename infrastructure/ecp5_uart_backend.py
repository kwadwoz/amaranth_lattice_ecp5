"""
ecp5_uart_backend.py — hardware backend skeleton for Lattice ECP5 via UART.

SKELETON ONLY — every method raises NotImplementedError.
This file defines the shape of the hardware backend and documents what each
method will eventually do. No real device I/O happens here.

When implemented, the flow will be:
    build()   — wrap the solver core in the frozen SATTop comm layer,
                synthesize via Amaranth -> yosys -> nextpnr-ecp5 -> ecppack,
                parse LUT/FF/BRAM counts from the nextpnr report and store
                them in a Stats object for later retrieval.
    program() — flash build/top.svf to the ECP5 via OpenOCD over JTAG
                (requires the FTDI FT2232H USB connection, not the CP2102).
    run()     — frame the CNF as a binary packet per contracts.py wire format,
                send over UART at 115200 baud via the CP2102 on
                /dev/tty.usbserial-0001, read back the result frame,
                decode the assignment bits, and return a Result.
"""

from __future__ import annotations

from .contracts import CNF, Result
from .fpga_interface import FPGAInterface


class ECP5UARTBackend(FPGAInterface):

    def build(self, core) -> None:
        """Wrap core in frozen comm layer and synthesize to bitstream."""
        raise NotImplementedError("hardware backend not yet implemented")

    def program(self) -> None:
        """Flash build/top.svf to the ECP5 via OpenOCD over JTAG."""
        raise NotImplementedError("hardware backend not yet implemented")

    def run(self, cnf: CNF, timeout: float = 30.0) -> Result:
        """Send CNF over UART, read result, return decoded Result."""
        raise NotImplementedError("hardware backend not yet implemented")
