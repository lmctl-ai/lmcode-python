let lo = 9007199254740992 * 1024;
let hi = lo - 1;
for (i in range(hi - 2, hi)) { t.int(i); }
for (i in range(lo, lo + 2)) { t.int(i); }
for (i in range(hi, lo)) { t.int(99); }
