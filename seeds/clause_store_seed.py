# clause_store_seed.py — Minimal clause store with EBR-mirrored timing.
#
# Data structure: Array-of-Arrays (register file, not actual EBR).
#   Seed uses registers for simplicity; agent migrates to Memory for EBR.
#   Read latency is deliberately 1-cycle registered to mirror EBR behaviour.
#
# Row layout (ROW_WIDTH bits per clause):
#   bits [7:0]                    = num_lits (actual count, ignoring padding)
#   bits [8+j*11 : 8+(j+1)*11]   = literal j  (j = 0 .. MAX_LITS-1)
#   Unused literal slots padded with 0x7FF.
#
# Literal encoding (same as unit_propagator):
#   11 bits: (var_index << 1) | sign,  var_index 0-based
#   sign: 0 = positive, 1 = negated
#   0x7FF = padding
#
# Clause address space:
#   0 .. num_original-1          → original clauses (immutable)
#   num_original .. learned_ptr-1 → active learned clauses
#
# Goal: correct clause storage with EBR-compatible timing. Agent optimises.

from amaranth import *

MAX_ORIGINAL = 32
MAX_LEARNED  = 32
MAX_CLAUSES  = MAX_ORIGINAL + MAX_LEARNED   # 64
MAX_LITS     = 4    # literal slots per clause
LIT_BITS     = 11   # 10-bit var index + 1-bit sign
ROW_WIDTH    = 8 + MAX_LITS * LIT_BITS      # 52

# EVOLVE-BLOCK-START

class ClauseStore(Elaboratable):
    """
    Clause store for CDCL SAT solver.

    Original clause loading (one-time init):
        For each clause C:
            Assert load_en, set load_clause=C, load_lit=j, load_data=literal for
            each literal j. Then pulse load_commit with load_num_lits = actual count.
            load_done pulses one cycle after load_commit.

    Reading a clause:
        Assert read_en with read_addr = clause index.
        read_data is valid the following cycle (read_valid goes high).
        read_data format: {lit3, lit2, lit1, lit0, num_lits}  (LSB = num_lits).

    Writing a learned clause:
        Pack into write_clause (ROW_WIDTH bits, same format as read_data).
        Assert write_en for one cycle. write_done pulses next cycle.
        write_addr_out captures the address used.

    Deletion (seed only removes last learned clause):
        Pulse delete_en. Decrements learned count by one.
    """

    def __init__(self, max_original=MAX_ORIGINAL, max_learned=MAX_LEARNED,
                 max_lits=MAX_LITS, lit_bits=LIT_BITS):
        self.max_original = max_original
        self.max_learned  = max_learned
        self.max_clauses  = max_original + max_learned
        self.max_lits     = max_lits
        self.lit_bits     = lit_bits
        rw                = 8 + max_lits * lit_bits
        self.row_width    = rw

        # Read port
        self.read_addr  = Signal(15)
        self.read_en    = Signal()
        self.read_data  = Signal(rw)   # valid one cycle after read_en
        self.read_valid = Signal()     # high when read_data is valid

        # Load port (original clauses, literal-by-literal staging)
        self.load_en       = Signal()
        self.load_clause   = Signal(range(max_original))
        self.load_lit      = Signal(range(max_lits))
        self.load_data     = Signal(lit_bits)
        self.load_commit   = Signal()   # pulse to finalise clause
        self.load_num_lits = Signal(8)

        # Write port (learned clauses, atomic single-cycle write)
        self.write_en       = Signal()
        self.write_clause   = Signal(rw)   # packed row: same format as read_data
        self.write_addr_out = Signal(15)
        self.write_done     = Signal()

        # Management
        self.load_start   = Signal()    # reserved; ignored in seed
        self.load_done    = Signal()    # output: pulses one cycle after load_commit
        self.num_original = Signal(15)  # output: count of original clauses
        self.num_learned  = Signal(15)  # output: count of active learned clauses
        self.delete_en    = Signal()

    def elaborate(self, platform):
        m = Module()

        mo = self.max_original
        mc = self.max_clauses
        ml = self.max_lits
        lb = self.lit_bits
        rw = self.row_width

        # Clause data (register file; init literals to padding value 0x7FF)
        clause_lits = Array([
            Array([Signal(lb, name=f"c{i}l{j}", init=(2**lb - 1)) for j in range(ml)])
            for i in range(mc)
        ])
        clause_nlit = Array([Signal(8, name=f"c{i}_n") for i in range(mc)])

        # Internal state
        num_orig    = Signal(15)
        learned_ptr = Signal(range(mc + 1))

        # Outputs driven from internal state
        m.d.comb += [
            self.num_original.eq(num_orig),
            self.num_learned.eq(learned_ptr - num_orig),
        ]

        # --- Read path ---
        # One Array per literal slot (outer mux over clause index).
        # Registered output adds 1-cycle latency matching EBR behaviour.
        nlit_mux  = Array([clause_nlit[i]     for i in range(mc)])
        lit_muxes = [Array([clause_lits[i][j] for i in range(mc)]) for j in range(ml)]

        read_comb = Signal(rw)
        m.d.comb += read_comb.eq(Cat(
            nlit_mux[self.read_addr],
            *[lit_muxes[j][self.read_addr] for j in range(ml)],
        ))
        m.d.sync += [
            self.read_data.eq(read_comb),
            self.read_valid.eq(self.read_en),
        ]

        # --- Load path (original clauses) ---
        with m.If(self.load_en):
            for ci in range(mo):
                with m.If(self.load_clause == ci):
                    for li in range(ml):
                        with m.If(self.load_lit == li):
                            m.d.sync += clause_lits[ci][li].eq(self.load_data)

        # Priority: load_commit > write_en > delete_en (only one active at a time)
        with m.If(self.load_commit):
            for ci in range(mo):
                with m.If(self.load_clause == ci):
                    m.d.sync += clause_nlit[ci].eq(self.load_num_lits)
            m.d.sync += [
                num_orig.eq(self.load_clause + 1),
                learned_ptr.eq(Mux(
                    self.load_clause + 1 > learned_ptr,
                    self.load_clause + 1,
                    learned_ptr,
                )),
            ]

        # load_done: ack one cycle after load_commit
        m.d.sync += self.load_done.eq(self.load_commit)

        # --- Write path (learned clauses) ---
        m.d.sync += self.write_done.eq(0)
        with m.If(~self.load_commit & self.write_en):
            for ci in range(mc):
                with m.If(learned_ptr == ci):
                    m.d.sync += clause_nlit[ci].eq(self.write_clause[:8])
                    for li in range(ml):
                        m.d.sync += clause_lits[ci][li].eq(
                            self.write_clause[8 + li * lb : 8 + (li + 1) * lb]
                        )
            m.d.sync += [
                self.write_addr_out.eq(learned_ptr),
                learned_ptr.eq(learned_ptr + 1),
                self.write_done.eq(1),
            ]

        # --- Delete (seed: trim last learned clause) ---
        with m.If(~self.load_commit & ~self.write_en
                  & self.delete_en & (learned_ptr > num_orig)):
            m.d.sync += learned_ptr.eq(learned_ptr - 1)

        return m

# EVOLVE-BLOCK-END


if __name__ == "__main__":
    from amaranth.back.rtlil import convert
    dut = ClauseStore()
    ports = [
        dut.read_addr, dut.read_en, dut.read_data, dut.read_valid,
        dut.load_en, dut.load_clause, dut.load_lit, dut.load_data,
        dut.load_commit, dut.load_num_lits,
        dut.write_en, dut.write_clause, dut.write_addr_out, dut.write_done,
        dut.load_start, dut.load_done,
        dut.num_original, dut.num_learned, dut.delete_en,
    ]
    print(convert(dut, ports=ports))
    print("Elaboration OK")
