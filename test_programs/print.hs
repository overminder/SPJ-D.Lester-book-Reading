head x y = x;

justNil x y = nil;

takeRest n car cdr = cons car (take (n - 1) cdr);

take n lis = if (n <= 0) nil
                (casePair lis
                   (takeRest n)
                   justNil);

printCons cont x y = printInt x (printComma (printList y cont));

printList lst cont = casePair lst
  (printCons cont)
  cont;

myList = cons 1 (cons 2 (cons 3 nil));

infList i = cons i (infList (i + 1));

myList2 = take 100 (infList 0);

main = printList myList2 (printNl nil);

