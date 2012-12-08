from pypy.rlib import jit

from spj.opdis import jit_getloc

driver = jit.JitDriver(greens=['pc', 'code'],
                       reds=['state'],
                       name='G-Machine-JitDriver',
                       virtualizables=['state'], # <-
                       get_printable_location=jit_getloc)


