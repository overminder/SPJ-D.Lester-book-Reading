
HSSRC = $(shell find . -name "*.hs")

HCFLAGS = --make

all : Demo-c ../interp/OpcodeDef.inc

Demo-c : Demo.hs $(HSSRC)
	ghc $< $(HCFLAGS) -o $@

MkOpcode-c : MkOpcode.hs $(HSSRC)
	ghc $< $(HCFLAGS) -o $@

../interp/OpcodeDef.inc : MkOpcode-c
	./MkOpcode-c > ../interp/OpcodeDef.inc

