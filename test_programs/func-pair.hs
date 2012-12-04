(.) f g x = f (g x);

mkPair car cdr getPair getNil = getPair car cdr;
mkNil          getPair getNil = getNil;

getCar car _ = car;
getCdr _ cdr = cdr;

k1 x y = y;

range n = if (n < 1)
             mkNil
             (mkPair n (range (n - 1)));

foldl combine init aList = aList (aList (foldlAux combine init)) init;
foldlAux combine init x xs = foldl combine (combine init x) xs;

sum = foldl (+) 0;

length aList = aList length_casePair 0;
length_casePair _ cdr = 1 + (length cdr);

length' aList = foldl (((+) 1) . k1) 0 aList;

someList = range 10;

main = 0;

