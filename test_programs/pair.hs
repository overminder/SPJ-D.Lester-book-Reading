
if_nil = 0;
if_cons x y = y;

main = casePair (cons 1 2) if_cons if_nil;

