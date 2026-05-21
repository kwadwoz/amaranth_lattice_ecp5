from amaranth import *
from amaranth.sim import Simulator


'''
a = Const(10, unsigned(16))


print(len(a))

'''


'''
from enum import Enum, unique


@unique

class Func(Enum):
    NONE = 0 
    ADD = 1 
    SUB = 2
    MUL = 3
    DIV = 4


print(Func.ADD())
'''


'''
class My_module(Elaboratable):
    def __init__(self):
        self.input_a = signal(8)

        self.input_b = signal(8)

        self.output = signal(8)

    def elaborate(self, platform):
        m = Module()

        m.d.com+= self.output.eq(self.input_a+ self.input_b)

        
        return m

'''


    

    # Lets implement a counter in Amaranth

'''
class My_counter(Elaboratable):
        
    # we have to define the width of the value we are using
    def __init__(self, width= 8):
        self.width = Signal(8)

        self.enable = Signal()
        self.reset = Signal()
        self.value = Signal(width)

    def elaborate(self, platform):
        m = Module()

        with m.If(self.reset):
            m.d.sync += self.value.eq(0)

        with m.Elif(self.enable):
            m.d.sync += self.value.eq(self.value + 1)

            
        return m
    
class two_counters(Elaboratable):
    def __init__(self):
        self.enable_a = Signal(8)
        self.enable_b = Signal(8)

        self.sum = Signal(9)

    def elaborate(self, platform):
        m = Module()

        counter_a= My_counter()
        counter_b = My_counter()


        m.submodules.counter_a = counter_a
        m.submodules.counter_b = counter_b

        m.d.comb+= counter_a.enable.eq(self.enable_a)
        m.d.comb+= counter_a.enable.eq(self.enable_b)

        m.d.comb+= self.sum.eq(counter_a.value + counter_b.value)

        
        return m





# 1. Create the top-level design
dut = two_counters()

# 2. Define the "testbench" (the sequence of actions)
async def testbench(ctx):
    # Set initial values
    ctx.set(dut.enable_a, 1)
    ctx.set(dut.enable_b, 0)
    
    # Run for 5 clock cycles
    for _ in range(5):
        await ctx.tick()
        print(f"Sum: {ctx.get(dut.sum)}")

    # Toggle signals
    ctx.set(dut.enable_a, 0)
    ctx.set(dut.enable_b, 1)

    for _ in range(5):
        await ctx.tick()
        print(f"Sum: {ctx.get(dut.sum)}")

# 3. Setup and Run Simulator
sim = Simulator(dut)
sim.add_clock(1e-6) # 1 MHz clock
sim.add_testbench(testbench)

# This creates a 'test.vcd' file you can open in GTKWave
with sim.write_vcd("test.vcd"):
    sim.run()


'''




#Finite State Machine


class Traffic_LIght(Elaboratable):
    def __init__(self):
        self.tick = Signal()
        self.red = Signal()
        self.green = Signal()
        self.yellow= Signal()


    def elaborate(self, platform):
        m = Module()


        with m.FSM():
            with m.State("RED"):
                m.d.comb+= self.red.eq(1)
                with m.If(self.tick):
                    m.next = "GREEN"
            
            with m.State("GREEN"):
                m.d.comb+=self.green.eq(1)
                with m.If(self.tick):
                    m.next = "YELllOW"


            with m.State("YELLOW"):
                m.d.comb+=self.green.eq(1)
                with m.If(self.tick):
                    m.next = "RED"
        return m

program = Traffic_LIght()

print(program.tick)