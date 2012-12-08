import struct
import random
from spj.interp import State

def test_decode_u8():
    for i in xrange(256):
        co = [chr(i)]
        s = State(co, None)
        assert s.decode_u8() == i
        assert s.pc == 1

def test_decode_i16_positive():
    for _ in xrange(100):
        i = random.randint(0, 128 * 256 - 1)
        co = [chr(i & 0xff), chr(i >> 8)]
        s = State(co, None)
        assert s.decode_i16() == i
        assert s.pc == 2

def test_decode_i16_negative():
    for _ in xrange(100):
        i = random.randint(-128 * 256, 0)
        co = [chr(i & 0xff), chr((i >> 8) & 0xff)]
        s = State(co, None)
        assert s.decode_i16() == i
        assert s.pc == 2

