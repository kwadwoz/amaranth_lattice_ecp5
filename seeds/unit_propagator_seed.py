# unit_propagator_seed.py — Minimal BCP (Boolean Constraint Propagation) seed.
#
# Algorithm: sequential clause scan, fixpoint loop.
#   - Scan every clause once per pass.
#   - If a clause has one unassigned literal and all others false → force it.
#   - Repeat passes until no new assignments are made (fixpoint).
#   - If all literals in a clause are false → conflict.
#
# Literal encoding (contracts.py convention):
#   byte = (var_index << 1) | sign
#   var_index: 0-based  (DIMACS var 1 → index 0)
#   sign: 0 = positive literal, 1 = negated literal
#   0xFF = padding (unused literal slot in clause)
#
# Goal: correct BCP, not fast BCP. Agent optimises from here.

from amaranth import *

MAX_VARS    = 32
MAX_CLAUSES = 32
MAX_LITS    = 4    # literal slots per clause; unused slots filled with 0xFF

# EVOLVE-BLOCK-START

class UnitPropagator(Elaboratable):
    """
    BCP engine. Iterates clauses, finds unit clauses, forces assignments.

    Call sequence:
        1. Load clauses via load_en / load_clause / load_lit / load_data.
        2. Set num_vars, num_clauses, assignment, assigned.
        3. Pulse start for one cycle.
        4. Wait for done (no more unit clauses) or conflict.
        5. Read assignment_out / assigned_out for updated state.
    """

    def __init__(self, max_vars=MAX_VARS, max_clauses=MAX_CLAUSES, max_lits=MAX_LITS):
        self.max_vars    = max_vars
        self.max_clauses = max_clauses
        self.max_lits    = max_lits

        # Control
        self.start       = Signal()
        self.num_vars    = Signal(range(max_vars + 1))
        self.num_clauses = Signal(range(max_clauses + 1))

        # Assignment input (one bit per variable, 0-based index)
        self.assignment  = Signal(max_vars)
        self.assigned    = Signal(max_vars)

        # Clause load port (write before pulsing start)
        self.load_en     = Signal()
        self.load_clause = Signal(range(max_clauses))
        self.load_lit    = Signal(range(max_lits))
        self.load_data   = Signal(8)

        # Outputs
        self.done            = Signal()
        self.conflict        = Signal()
        self.conflict_clause = Signal(range(max_clauses))

        # Forced assignment stream (valid for one cycle each)
        self.forced_var   = Signal(range(max_vars + 1))  # 1-based; 0 = none
        self.forced_val   = Signal()
        self.forced_valid = Signal()

        # Updated assignment after propagation
        self.assignment_out = Signal(max_vars)
        self.assigned_out   = Signal(max_vars)

    def elaborate(self, platform):
        m = Module()

        mv = self.max_vars
        mc = self.max_clauses
        ml = self.max_lits

        # Clause database: clause_db[clause_idx][lit_idx] = 8-bit literal byte
        clause_db = Array([
            Array([Signal(8, name=f"c{i}l{j}") for j in range(ml)])
            for i in range(mc)
        ])

        # Working assignment (updated as variables are forced)
        asgn  = Signal(mv, name="asgn")
        asgnd = Signal(mv, name="asgnd")

        # Scan state
        clause_idx  = Signal(range(mc + 1))
        lit_idx     = Signal(range(ml + 1))

        # Per-clause tracking
        unass_count = Signal(range(ml + 1))
        unit_var    = Signal(range(mv), name="unit_var")   # 0-based index
        unit_val    = Signal(name="unit_val")              # forced value

        changed = Signal()   # did we force anything this pass?

        # Clause database write port
        with m.If(self.load_en):
            m.d.sync += clause_db[self.load_clause][self.load_lit].eq(self.load_data)

        # Outputs always reflect working copies
        m.d.comb += [
            self.assignment_out.eq(asgn),
            self.assigned_out.eq(asgnd),
        ]

        # Current literal under inspection
        cur_lit = Signal(8, name="cur_lit")
        m.d.comb += cur_lit.eq(clause_db[clause_idx][lit_idx])

        # Decompose literal
        is_padding   = Signal()
        var_assigned = Signal()
        var_val      = Signal()
        lit_val      = Signal()
        m.d.comb += [
            is_padding.eq(cur_lit == 0xFF),
            var_assigned.eq(asgnd.bit_select(cur_lit[1:], 1)),
            var_val.eq(asgn.bit_select(cur_lit[1:], 1)),
            lit_val.eq(var_val ^ cur_lit[0]),   # True when literal is satisfied
        ]

        with m.FSM():

            with m.State("IDLE"):
                m.d.sync += [
                    self.done.eq(0),
                    self.conflict.eq(0),
                    self.forced_valid.eq(0),
                ]
                with m.If(self.start):
                    m.d.sync += [
                        asgn.eq(self.assignment),
                        asgnd.eq(self.assigned),
                        clause_idx.eq(0),
                        changed.eq(0),
                    ]
                    m.next = "SCAN_CLAUSE"

            with m.State("SCAN_CLAUSE"):
                m.d.sync += self.forced_valid.eq(0)
                with m.If(clause_idx == self.num_clauses):
                    # Completed one full pass over all clauses
                    with m.If(changed):
                        # At least one variable was forced — do another pass
                        m.d.sync += [
                            clause_idx.eq(0),
                            changed.eq(0),
                        ]
                    with m.Else():
                        # Fixpoint: nothing new was forced
                        m.d.sync += self.done.eq(1)
                        m.next = "IDLE"
                with m.Else():
                    m.d.sync += [
                        lit_idx.eq(0),
                        unass_count.eq(0),
                    ]
                    m.next = "SCAN_LIT"

            with m.State("SCAN_LIT"):
                with m.If(lit_idx == ml):
                    # All literal slots scanned — no true literal found
                    with m.If(unass_count == 0):
                        # Every non-padding literal is false → conflict
                        m.d.sync += [
                            self.conflict.eq(1),
                            self.conflict_clause.eq(clause_idx),
                        ]
                        m.next = "IDLE"
                    with m.Elif(unass_count == 1):
                        # Exactly one unassigned literal, rest false → unit clause
                        # Force unit_var = unit_val (0-based index)
                        for vi in range(mv):
                            with m.If(unit_var == vi):
                                m.d.sync += [
                                    asgn[vi].eq(unit_val),
                                    asgnd[vi].eq(1),
                                ]
                        m.d.sync += [
                            self.forced_var.eq(unit_var + 1),   # convert to 1-based
                            self.forced_val.eq(unit_val),
                            self.forced_valid.eq(1),
                            changed.eq(1),
                            clause_idx.eq(clause_idx + 1),
                        ]
                        m.next = "SCAN_CLAUSE"
                    with m.Else():
                        # More than one unassigned → undecided, move on
                        m.d.sync += clause_idx.eq(clause_idx + 1)
                        m.next = "SCAN_CLAUSE"

                with m.Else():
                    # Evaluate current literal
                    with m.If(is_padding):
                        # Unused slot — skip
                        m.d.sync += lit_idx.eq(lit_idx + 1)
                    with m.Elif(var_assigned & lit_val):
                        # Literal is true → clause satisfied, skip rest of clause
                        m.d.sync += clause_idx.eq(clause_idx + 1)
                        m.next = "SCAN_CLAUSE"
                    with m.Elif(var_assigned & ~lit_val):
                        # Literal is false — count it
                        m.d.sync += lit_idx.eq(lit_idx + 1)
                    with m.Else():
                        # Literal is unassigned — record as potential unit literal
                        m.d.sync += [
                            unass_count.eq(unass_count + 1),
                            unit_var.eq(cur_lit[1:]),         # 0-based var index
                            unit_val.eq(cur_lit[0] ^ 1),      # force literal True: ~sign
                            lit_idx.eq(lit_idx + 1),
                        ]

        return m

# EVOLVE-BLOCK-END


if __name__ == "__main__":
    # Elaborate to check for syntax errors
    from amaranth.back.rtlil import convert
    dut = UnitPropagator()
    ports = [
        dut.start, dut.num_vars, dut.num_clauses,
        dut.assignment, dut.assigned,
        dut.load_en, dut.load_clause, dut.load_lit, dut.load_data,
        dut.done, dut.conflict, dut.conflict_clause,
        dut.forced_var, dut.forced_val, dut.forced_valid,
        dut.assignment_out, dut.assigned_out,
    ]
    print(convert(dut, ports=ports))
    print("Elaboration OK")
