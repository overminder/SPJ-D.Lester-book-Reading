k x y = x;
k1 x y = y;

pair x y f = f x y;

fst p = p k;
snd p = p k1;

f x y = let a = pair x y;
         in fst a;

main = f 1 2;

