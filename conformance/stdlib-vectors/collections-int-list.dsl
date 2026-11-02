let x = int_list().add(7).add(-2).add(7);
t.int(x.len()); t.int(x.at(1)); t.bool(x.contains(7)); t.int(x.index_of(7));
t.bool(x.contains(9)); t.int(x.index_of(9));
x.set(0, 11).add(0); for (n in x) { t.int(n); }
t.int(x.clear().add(42).len()); t.int(x.at(0));
