# test_verifier_hw.py — run a CNF through the FPGA and verify the result.
#
# Usage:
#   python test_verifier_hw.py test_simple.cnf        # SAT formula
#   python test_verifier_hw.py test_unsat.cnf         # UNSAT formula
#
# With hardware_stub_ecp5.py loaded, the FPGA always returns UNSAT:
#   SAT formula  -> FPGA wrong  -> verifier returns CORRECTNESS_VIOLATION
#   UNSAT formula-> FPGA right  -> verifier returns VERIFIED

import sys
from sat_experiment import parse_dimacs, run_experiment
from verifier import verify

cnf_file = sys.argv[1] if len(sys.argv) > 1 else "test_simple.cnf"

_, clauses = parse_dimacs(cnf_file)
result = run_experiment(cnf_file)

verdict = verify(clauses, result, cross_check_unsat=True)

print(f"Formula : {cnf_file}")
print(f"FPGA    : {result}")
print(f"Verdict : {verdict}")
