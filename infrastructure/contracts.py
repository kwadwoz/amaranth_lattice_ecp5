"""
contracts.py — single source of truth for result types, wire-format constants,
and the in-memory CNF representation shared across all backends.

Two sections of this file are NOT finalized and must not be duplicated elsewhere:
  - Result / Stats types
  - Wire-format layout constants  (marked # TODO: CONFIRM WITH TEAMMATE)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional



# Result types


class Status(Enum):
    SAT     = auto()
    UNSAT   = auto()
    TIMEOUT = auto()
    ERROR   = auto()   # ERROR != UNSAT: ERROR means the harness broke,
                       # UNSAT means the solver ran and found no solution.


@dataclass
class Stats:
    solve_time_s: float           = 0.0
    lut:          Optional[int]   = None   # filled by hardware backend post-build
    ff:           Optional[int]   = None
    bram:         Optional[int]   = None
    fmax_mhz:     Optional[float] = None


@dataclass
class Result:
    status:     Status
    assignment: Optional[list[bool]] = None  # index 0 = var 1 … index N-1 = var N
                                             # present only when status is SAT
    stats:      Stats                = field(default_factory=Stats)
    error_msg:  Optional[str]        = None



# Wire-format layout constants
# TODO: CONFIRM WITH TEAMMATE before the hardware backend is implemented.
# All field-width and encoding decisions live here and NOWHERE ELSE.


FORMAT_VERSION     = 1

ENDIANNESS         = "little"   # TODO: confirm byte order for multi-byte fields

VAR_COUNT_BYTES    = 1          # TODO: confirm — currently 1 byte (max 255 vars)
CLAUSE_COUNT_BYTES = 1          # TODO: confirm — currently 1 byte (max 255 clauses)
LITERAL_BYTES      = 1          # TODO: confirm — currently 1 byte per literal

# Literal encoding (host → FPGA):
#   unsigned byte = (var_index << 1) | sign
#   var_index is 0-based  (DIMACS var 1 → index 0)
#   sign: 0 = positive literal, 1 = negated literal
#   Example: DIMACS  2 → 0b00000010 (0x02)
#            DIMACS -2 → 0b00000011 (0x03)
# TODO: confirm encoding with Andrew — sat_experiment.py uses a different
#       scheme (MSB for sign, 1-based var); one must win before hw is wired up.

# Assignment readback (FPGA → host):
#   1 bit per variable, variables 1..N packed LSB-first within each byte.
#   Total bytes = ceil(N / 8).
# TODO: confirm packing order with Andrew``.

START_MARKER = 0xAA
END_MARKER   = 0xFF
CLAUSE_TERM  = 0x00


# In-memory CNF representation


@dataclass
class CNF:
    """In-memory CNF formula in DIMACS convention.

    clauses: list of lists of non-zero ints.
             Positive int i  → variable i (1-based).
             Negative int -i → negation of variable i.
    """
    num_vars: int
    clauses:  list[list[int]]

    @property
    def num_clauses(self) -> int:
        return len(self.clauses)


def read_dimacs(path: str) -> CNF:
    """Minimal DIMACS CNF reader.

    Handles comments (c ...), the problem line (p cnf N M), and clause lines.
    Clauses may span multiple lines; 0 terminates each clause.
    """
    num_vars = 0
    clauses: list[list[int]] = []
    current: list[int] = []

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('c'):
                continue
            if line.startswith('p'):
                parts    = line.split()
                num_vars = int(parts[2])
                continue
            for token in line.split():
                lit = int(token)
                if lit == 0:
                    if current:
                        clauses.append(current)
                        current = []
                else:
                    current.append(lit)

    return CNF(num_vars=num_vars, clauses=clauses)
