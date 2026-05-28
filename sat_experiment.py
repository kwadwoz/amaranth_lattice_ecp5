import serial
import sys

SERIAL_PORT = '/dev/tty.usbserial-0001'
BAUD_RATE   = 115200

# Protocol constants
START_MARKER = 0xAA
END_MARKER   = 0xFF
CLAUSE_TERM  = 0x00
RESULT_SAT   = 0x01
RESULT_UNSAT = 0x00


def parse_dimacs(filepath):
    """Parse a DIMACS CNF file into (num_vars, clauses).

    DIMACS format:
        c  comment line (ignored)
        p cnf <num_vars> <num_clauses>
        1 -2 3 0      <- clause: x1 OR NOT x2 OR x3, terminated by 0
        -1 2 0        <- clause: NOT x1 OR x2

    A clause may span multiple lines; 0 always terminates it.
    Returns num_vars (int) and clauses (list of list of int).
    """
    num_vars = 0
    clauses  = []
    current  = []

    with open(filepath) as f:
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

    return num_vars, clauses


def encode_literal(lit):
    """Encode a DIMACS literal as one byte.

    Bit 7 = sign (0 positive, 1 negated)
    Bits 6-0 = variable number (1-127)

    Example:  x2 ->  0x02,  NOT x2 -> 0x82
    """
    if lit > 0:
        return lit & 0x7F
    else:
        return ((-lit) & 0x7F) | 0x80


def encode_binary(num_vars, clauses):
    """Encode a CNF formula as the binary UART protocol.

    Packet layout:
        0xAA          start marker
        N             number of variables (1 byte)
        M             number of clauses   (1 byte)
        [literals...] variable-length literals per clause
        0x00          clause terminator
        ...           (repeat for each clause)
        0xFF          end of formula
    """
    packet = bytearray()

    packet.append(START_MARKER)
    packet.append(num_vars & 0xFF)
    packet.append(len(clauses) & 0xFF)

    for clause in clauses:
        for lit in clause:
            packet.append(encode_literal(lit))
        packet.append(CLAUSE_TERM)

    packet.append(END_MARKER)
    return bytes(packet)


def decode_response(data, num_vars):
    """Decode FPGA response bytes into a result dict.

    Response layout:
        0x00          UNSAT
        0x01          SAT
        [N bytes]     variable assignments (bit 7 = value, bits 6-0 = var number)
        0xFF          end marker
    """
    if not data:
        return {'result': 'TIMEOUT'}

    if data[0] == RESULT_UNSAT:
        return {'result': 'UNSAT'}

    if data[0] == RESULT_SAT:
        assignment = {}
        for byte in data[1:]:
            if byte == END_MARKER:
                break
            var       = byte & 0x7F
            value     = bool(byte >> 7)
            assignment[var] = value
        return {'result': 'SAT', 'assignment': assignment}

    return {'result': 'ERROR', 'raw': data.hex()}


def run_experiment(cnf_file, port=SERIAL_PORT, baud=BAUD_RATE):
    num_vars, clauses = parse_dimacs(cnf_file)

    print(f"Formula : {num_vars} variables, {len(clauses)} clauses")

    if num_vars > 127:
        raise ValueError(f"Too many variables: {num_vars} (max 127)")
    if len(clauses) > 255:
        raise ValueError(f"Too many clauses: {len(clauses)} (max 255)")

    packet = encode_binary(num_vars, clauses)
    print(f"Packet  : {len(packet)} bytes")
    print(f"Hex     : {packet.hex()}")

    s = serial.Serial(port, baud, timeout=5)
    s.write(packet)

    # 1 result byte + num_vars assignment bytes + 1 end marker
    raw = s.read(1 + num_vars + 1)
    s.close()

    result = decode_response(raw, num_vars)

    if result['result'] == 'SAT':
        print("Result  : SAT")
        for var, val in sorted(result['assignment'].items()):
            print(f"  x{var} = {'True' if val else 'False'}")
    elif result['result'] == 'UNSAT':
        print("Result  : UNSAT")
    else:
        print(f"Result  : {result}")

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python sat_experiment.py <formula.cnf>")
        sys.exit(1)
    run_experiment(sys.argv[1])
