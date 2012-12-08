#!/usr/bin/env python

import sys

from spj.parser import read_program
from spj.gmcompile import compile
from spj.opdis import dis

source = sys.stdin.read()
ast = read_program(source)
state = compile(ast)

for sc_addr in state.env.itervalues():
    sc = sc_addr.node
    if not sc.name.startswith('PRIM_'): # is not a primitive
        dis(sc, state.names)
        print

