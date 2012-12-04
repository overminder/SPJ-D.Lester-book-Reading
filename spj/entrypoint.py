from pypy.rlib.streamio import fdopen_as_stream

from spj.parser import read_program
from spj.language import ppr
from spj.timc import compile
from spj.errors import InterpError

def main(argv):
    stdin = fdopen_as_stream(0, 'r')
    source = stdin.readall()
    try:
        ast = read_program(source)
        code = compile(ast)
        result = code.eval()
    except InterpError as e:
        print e.what
        return 1

    print result.to_s()
    return 0

