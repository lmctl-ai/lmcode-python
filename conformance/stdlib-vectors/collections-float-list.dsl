let nan = 0.0 / 0.0;
let x = float_list().add(1.5).add(nan).add(-0.0);
t.int(x.len()); t.float(x.at(0)); t.bool(x.contains(nan)); t.int(x.index_of(nan));
t.bool(x.contains(0.0)); t.int(x.index_of(0.0)); t.float(x.at(2));
x.set(0, 2.5); t.float(x.at(0)); t.bool(x.at(1) == x.at(1));
t.int(x.clear().add(3.5).len()); t.float(x.at(0));
