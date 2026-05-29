"""Simulation tests for ClauseStore seed."""

import pytest
from amaranth.sim import Simulator
from seeds.clause_store_seed import ClauseStore, LIT_BITS


def lit(var_idx, positive=True):
    """Encode an 11-bit literal. var_idx is 0-based."""
    return (var_idx << 1) | (0 if positive else 1)


def pack_row(num_lits, literals, max_lits=4, lit_bits=LIT_BITS):
    """Pack a clause into ROW_WIDTH bits: {lit3,..,lit0, num_lits}."""
    row = num_lits & 0xFF
    for j, lv in enumerate(literals[:max_lits]):
        row |= (lv & ((1 << lit_bits) - 1)) << (8 + j * lit_bits)
    # pad unused slots with 0x7FF
    for j in range(len(literals), max_lits):
        row |= 0x7FF << (8 + j * lit_bits)
    return row


def unpack_row(row, max_lits=4, lit_bits=LIT_BITS):
    """Return (num_lits, [lit0, lit1, lit2, lit3]) from a packed row."""
    num_lits = row & 0xFF
    lits = [(row >> (8 + j * lit_bits)) & ((1 << lit_bits) - 1)
            for j in range(max_lits)]
    return num_lits, lits


async def load_clause(ctx, dut, clause_idx, literals):
    """Load one clause into the store via the load port and commit it."""
    for j, lv in enumerate(literals):
        ctx.set(dut.load_en, 1)
        ctx.set(dut.load_clause, clause_idx)
        ctx.set(dut.load_lit, j)
        ctx.set(dut.load_data, lv)
        await ctx.tick()
    ctx.set(dut.load_en, 0)
    # Commit
    ctx.set(dut.load_commit, 1)
    ctx.set(dut.load_num_lits, len(literals))
    await ctx.tick()
    ctx.set(dut.load_commit, 0)
    await ctx.tick()   # wait for load_done pulse


async def read_clause(ctx, dut, addr):
    """Issue a read and return (num_lits, lits) one cycle later.

    In the Amaranth simulator ctx.get() returns post-edge values, so
    read_valid and read_data are valid immediately after the tick where
    read_en was high — not the tick after.
    """
    ctx.set(dut.read_en, 1)
    ctx.set(dut.read_addr, addr)
    await ctx.tick()
    # read_valid and read_data are valid NOW (post-edge of the tick with read_en=1)
    assert ctx.get(dut.read_valid), "read_valid should be high"
    result = unpack_row(ctx.get(dut.read_data), dut.max_lits, dut.lit_bits)
    ctx.set(dut.read_en, 0)
    await ctx.tick()
    return result


# ---------------------------------------------------------------------------
# Test 1: load one clause and read it back
# ---------------------------------------------------------------------------

def test_load_and_read_single_clause():
    dut = ClauseStore()

    async def testbench(ctx):
        clause = [lit(0, True), lit(1, False)]    # x0 ∨ ¬x1
        await load_clause(ctx, dut, clause_idx=0, literals=clause)

        num_lits, lits = await read_clause(ctx, dut, addr=0)

        assert num_lits == 2
        assert lits[0] == lit(0, True)
        assert lits[1] == lit(1, False)
        assert lits[2] == 0x7FF, "unused slot should be padding"
        assert lits[3] == 0x7FF

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(testbench)
    with sim.write_vcd("/tmp/test_cs_single.vcd"):
        sim.run()


# ---------------------------------------------------------------------------
# Test 2: load multiple original clauses, read each back
# ---------------------------------------------------------------------------

def test_load_and_read_multiple_clauses():
    dut = ClauseStore()

    clauses = [
        [lit(0, True), lit(1, True)],             # clause 0: x0 ∨ x1
        [lit(1, False), lit(2, True)],            # clause 1: ¬x1 ∨ x2
        [lit(0, False), lit(1, False), lit(2, False)],  # clause 2: ¬x0 ∨ ¬x1 ∨ ¬x2
    ]

    async def testbench(ctx):
        for i, c in enumerate(clauses):
            await load_clause(ctx, dut, clause_idx=i, literals=c)

        for i, c in enumerate(clauses):
            num_lits, lits = await read_clause(ctx, dut, addr=i)
            assert num_lits == len(c), f"clause {i}: num_lits mismatch"
            for j, lv in enumerate(c):
                assert lits[j] == lv, f"clause {i} lit {j}: {lits[j]} != {lv}"

        assert ctx.get(dut.num_original) == 3

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(testbench)
    with sim.write_vcd("/tmp/test_cs_multi.vcd"):
        sim.run()


# ---------------------------------------------------------------------------
# Test 3: write a learned clause and read it back
# ---------------------------------------------------------------------------

def test_write_learned_clause():
    dut = ClauseStore()

    async def testbench(ctx):
        # First load one original clause so num_original = 1
        await load_clause(ctx, dut, clause_idx=0, literals=[lit(0, True)])
        orig_count = ctx.get(dut.num_original)
        assert orig_count == 1

        # Write a learned clause
        learned = [lit(2, False), lit(3, True)]
        row = pack_row(len(learned), learned, dut.max_lits, dut.lit_bits)
        ctx.set(dut.write_en, 1)
        ctx.set(dut.write_clause, row)
        await ctx.tick()
        # write_done and write_addr_out are valid NOW (post-edge of tick with write_en=1)
        assert ctx.get(dut.write_done), "write_done should pulse"
        written_addr = ctx.get(dut.write_addr_out)
        assert written_addr == 1, f"learned clause should land at addr 1, got {written_addr}"
        assert ctx.get(dut.num_learned) == 1
        ctx.set(dut.write_en, 0)
        await ctx.tick()

        # Read it back
        num_lits, lits = await read_clause(ctx, dut, addr=written_addr)
        assert num_lits == 2
        assert lits[0] == lit(2, False)
        assert lits[1] == lit(3, True)

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(testbench)
    with sim.write_vcd("/tmp/test_cs_learned.vcd"):
        sim.run()


# ---------------------------------------------------------------------------
# Test 4: original clauses are unaffected by a learned clause write
# ---------------------------------------------------------------------------

def test_original_clauses_preserved_after_learned_write():
    dut = ClauseStore()

    async def testbench(ctx):
        orig = [lit(5, True), lit(6, False)]
        await load_clause(ctx, dut, clause_idx=0, literals=orig)

        learned = [lit(7, True)]
        row = pack_row(len(learned), learned, dut.max_lits, dut.lit_bits)
        ctx.set(dut.write_en, 1)
        ctx.set(dut.write_clause, row)
        await ctx.tick()
        ctx.set(dut.write_en, 0)
        await ctx.tick()
        # Original clause unchanged
        num_lits, lits = await read_clause(ctx, dut, addr=0)
        assert num_lits == 2
        assert lits[0] == lit(5, True)
        assert lits[1] == lit(6, False)

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(testbench)
    with sim.write_vcd("/tmp/test_cs_preserve.vcd"):
        sim.run()


# ---------------------------------------------------------------------------
# Test 5: read_valid tracks read_en with 1-cycle latency
# ---------------------------------------------------------------------------

def test_read_valid_latency():
    dut = ClauseStore()

    async def testbench(ctx):
        await load_clause(ctx, dut, clause_idx=0, literals=[lit(0, True)])

        # read_valid should NOT be high before a read
        await ctx.tick()
        assert ctx.get(dut.read_valid) == 0

        # Assert read_en; ctx.get() returns post-edge values so read_valid is
        # already high after the same tick where read_en was 1 (flip-flop captures
        # read_en on the rising edge; output visible immediately post-edge).
        ctx.set(dut.read_en, 1)
        ctx.set(dut.read_addr, 0)
        await ctx.tick()
        assert ctx.get(dut.read_valid) == 1, "read_valid should be high post-edge"
        ctx.set(dut.read_en, 0)
        await ctx.tick()
        assert ctx.get(dut.read_valid) == 0, "read_valid should drop after read_en deasserted"

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(testbench)
    with sim.write_vcd("/tmp/test_cs_latency.vcd"):
        sim.run()


# ---------------------------------------------------------------------------
# Test 6: delete decrements num_learned
# ---------------------------------------------------------------------------

def test_delete_decrements_learned_count():
    dut = ClauseStore()

    async def testbench(ctx):
        await load_clause(ctx, dut, clause_idx=0, literals=[lit(0, True)])

        # Write two learned clauses
        for lv in [lit(1, True), lit(2, True)]:
            row = pack_row(1, [lv], dut.max_lits, dut.lit_bits)
            ctx.set(dut.write_en, 1)
            ctx.set(dut.write_clause, row)
            await ctx.tick()
            ctx.set(dut.write_en, 0)
            await ctx.tick()

        assert ctx.get(dut.num_learned) == 2

        # Delete one
        ctx.set(dut.delete_en, 1)
        await ctx.tick()
        ctx.set(dut.delete_en, 0)
        await ctx.tick()

        assert ctx.get(dut.num_learned) == 1

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(testbench)
    with sim.write_vcd("/tmp/test_cs_delete.vcd"):
        sim.run()
