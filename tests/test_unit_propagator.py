"""Simulation tests for UnitPropagator BCP seed."""

import pytest
from amaranth.sim import Simulator
from seeds.unit_propagator_seed import UnitPropagator


def lit(var_idx, positive=True):
    """Encode a literal. var_idx is 0-based. sign=0 positive, sign=1 negated."""
    return (var_idx << 1) | (0 if positive else 1)


def load_clause_db(ctx, dut, clauses):
    """Load clauses into hardware. Each clause is a list of literal bytes."""
    for ci, clause in enumerate(clauses):
        padded = clause + [0xFF] * (dut.max_lits - len(clause))
        for li, byte in enumerate(padded):
            ctx.set(dut.load_en, 1)
            ctx.set(dut.load_clause, ci)
            ctx.set(dut.load_lit, li)
            ctx.set(dut.load_data, byte)
    ctx.set(dut.load_en, 0)


async def run_bcp(ctx, dut, clauses, assignment, assigned, max_cycles=200):
    """Load clauses, start BCP, run until done or conflict. Returns final ctx."""
    # Load clause DB (combinatorial writes take effect next tick)
    for ci, clause in enumerate(clauses):
        padded = clause + [0xFF] * (dut.max_lits - len(clause))
        for li, byte in enumerate(padded):
            ctx.set(dut.load_en, 1)
            ctx.set(dut.load_clause, ci)
            ctx.set(dut.load_lit, li)
            ctx.set(dut.load_data, byte)
            await ctx.tick()
    ctx.set(dut.load_en, 0)
    await ctx.tick()

    ctx.set(dut.assignment, assignment)
    ctx.set(dut.assigned, assigned)
    ctx.set(dut.num_vars, dut.max_vars)
    ctx.set(dut.num_clauses, len(clauses))
    ctx.set(dut.start, 1)
    await ctx.tick()
    ctx.set(dut.start, 0)

    for _ in range(max_cycles):
        await ctx.tick()
        if ctx.get(dut.done) or ctx.get(dut.conflict):
            return
    raise TimeoutError("BCP did not finish within cycle budget")


# ---------------------------------------------------------------------------
# Test 1: unit clause — single unassigned positive literal
# Clause: (x0)  →  x0 unassigned  →  force x0 = True
# ---------------------------------------------------------------------------

def test_unit_clause_positive():
    dut = UnitPropagator()

    async def testbench(ctx):
        await run_bcp(ctx, dut, [[lit(0, True)]], assignment=0, assigned=0)

        assert ctx.get(dut.done), "Expected done"
        asgn  = ctx.get(dut.assignment_out)
        asgnd = ctx.get(dut.assigned_out)
        assert (asgnd >> 0) & 1 == 1, "x0 should be assigned"
        assert (asgn  >> 0) & 1 == 1, "x0 should be True"

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(testbench)
    with sim.write_vcd("/tmp/test_unit_pos.vcd"):
        sim.run()


# ---------------------------------------------------------------------------
# Test 2: unit clause — single unassigned negated literal
# Clause: (¬x1)  →  x1 unassigned  →  force x1 = False
# ---------------------------------------------------------------------------

def test_unit_clause_negated():
    dut = UnitPropagator()

    async def testbench(ctx):
        await run_bcp(ctx, dut, [[lit(1, False)]], assignment=0, assigned=0)

        assert ctx.get(dut.done), "Expected done"
        asgn  = ctx.get(dut.assignment_out)
        asgnd = ctx.get(dut.assigned_out)
        assert (asgnd >> 1) & 1 == 1, "x1 should be assigned"
        assert (asgn  >> 1) & 1 == 0, "x1 should be False"

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(testbench)
    with sim.write_vcd("/tmp/test_unit_neg.vcd"):
        sim.run()


# ---------------------------------------------------------------------------
# Test 3: satisfied clause — no propagation
# Clause: (x0 ∨ x1), x0 already True  →  clause satisfied, x1 stays unforced
# ---------------------------------------------------------------------------

def test_satisfied_clause_no_propagation():
    dut = UnitPropagator()

    async def testbench(ctx):
        clause = [lit(0, True), lit(1, True)]
        # x0=True and assigned; x1 unassigned
        await run_bcp(ctx, dut, [clause], assignment=0b01, assigned=0b01)

        assert ctx.get(dut.done), "Expected done"
        asgnd = ctx.get(dut.assigned_out)
        assert (asgnd >> 1) & 1 == 0, "x1 should remain unassigned"

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(testbench)
    with sim.write_vcd("/tmp/test_satisfied.vcd"):
        sim.run()


# ---------------------------------------------------------------------------
# Test 4: conflict — all literals false
# Clause: (x0 ∨ x1), x0=False, x1=False  →  conflict
# ---------------------------------------------------------------------------

def test_conflict_all_false():
    dut = UnitPropagator()

    async def testbench(ctx):
        clause = [lit(0, True), lit(1, True)]
        await run_bcp(ctx, dut, [clause], assignment=0b00, assigned=0b11)

        assert ctx.get(dut.conflict), "Expected conflict"
        assert ctx.get(dut.conflict_clause) == 0

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(testbench)
    with sim.write_vcd("/tmp/test_conflict.vcd"):
        sim.run()


# ---------------------------------------------------------------------------
# Test 5: chain propagation — two-step fixpoint
# Clauses: (x0),  (¬x0 ∨ x1)
# Pass 1: clause 0 is unit → force x0=True
# Pass 2: clause 1 now has ¬x0 false and x1 unassigned → force x1=True
# ---------------------------------------------------------------------------

def test_chain_propagation():
    dut = UnitPropagator()

    async def testbench(ctx):
        clauses = [
            [lit(0, True)],
            [lit(0, False), lit(1, True)],
        ]
        await run_bcp(ctx, dut, clauses, assignment=0, assigned=0)

        assert ctx.get(dut.done), "Expected done"
        asgn  = ctx.get(dut.assignment_out)
        asgnd = ctx.get(dut.assigned_out)
        assert (asgnd >> 0) & 1 == 1 and (asgn >> 0) & 1 == 1, "x0 should be True"
        assert (asgnd >> 1) & 1 == 1 and (asgn >> 1) & 1 == 1, "x1 should be True"

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(testbench)
    with sim.write_vcd("/tmp/test_chain.vcd"):
        sim.run()


# ---------------------------------------------------------------------------
# Test 6: no-op — all clauses already satisfied
# Clause: (x0 ∨ x1), both assigned True  →  done immediately, no forcing
# ---------------------------------------------------------------------------

def test_no_propagation_needed():
    dut = UnitPropagator()

    async def testbench(ctx):
        clause = [lit(0, True), lit(1, True)]
        await run_bcp(ctx, dut, [clause], assignment=0b11, assigned=0b11)

        assert ctx.get(dut.done), "Expected done"
        assert not ctx.get(dut.conflict), "No conflict expected"

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(testbench)
    with sim.write_vcd("/tmp/test_noop.vcd"):
        sim.run()
