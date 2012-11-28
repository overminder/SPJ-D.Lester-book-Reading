main = if_not_zero 0 lots_of_cal 2;

lots_of_cal = twice twice twice twice id 3;

twice f = compose f f;

compose f g x = f (g x);

id x = x;

