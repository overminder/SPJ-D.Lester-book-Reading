
myPair = Pack{1, 2} 123 321;

main = case myPair of
  <1> x y -> x;
  <2> -> 0;;

