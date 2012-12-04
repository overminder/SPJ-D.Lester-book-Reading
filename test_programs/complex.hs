
main = myid1 1;

myid = s k k;
myid1 = myid myid;

id x = x;

k x y = x;

k1 x y = y;

s f g x = f x (g x);

compose f g x = f (g x);

twice f = compose f f;

