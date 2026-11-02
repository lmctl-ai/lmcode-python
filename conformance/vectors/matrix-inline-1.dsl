fn twice_plus(x: int) -> int { let y = x * 2; return y + 1; }
t.int(twice_plus(bound(-3))); t.int(twice_plus(bound(-2)));
