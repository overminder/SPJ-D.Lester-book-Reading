#!/usr/bin/env python

import sys
from spj.entrypoint import main

def target(driver, *argl):
    driver.exe_name = 'runspj-%(backend)s'
    return main, None

if __name__ == '__main__':
    sys.exit(main(sys.argv))

