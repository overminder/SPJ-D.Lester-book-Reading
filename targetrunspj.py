#!/usr/bin/env python

import sys
from spj.entrypoint import main

def jitpolicy(driver):
    from pypy.jit.codewriter.policy import JitPolicy
    return JitPolicy()

def target(driver, *argl):
    driver.exe_name = 'runspj-%(backend)s'
    return main, None

if __name__ == '__main__':
    sys.exit(main(sys.argv))

