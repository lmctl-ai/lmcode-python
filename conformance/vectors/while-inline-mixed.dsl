fn step(n: int) -> int { let out = 0; while (out < n) { out = out + 1; continue; } return out; }
fn pred(n: int) -> bool { for (j in range(0, 1)) { while (true) { break; } continue; } return n < 2; }
for (i in range(0, 2)) {
 t.int(100 + step(i));
 for (x in xs) { while (true) { t.int(i * 10 + x); break; } if (x == 1) { continue; } if (x == 2) { break; } }
}
let n = 0; while (pred(n)) { n = n + 1; continue; } t.int(n);
while (false) {}
for (k in range(0, 3)) { break; }
for (x in xs) { if (x == 3) { continue; } t.int(x); }
