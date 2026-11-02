let x = str_list();
t.int(x.len());
x.add(bytes("ff00")).add("é").add(bytes("ff00"));
t.int(x.len()); t.bool(x.contains(bytes("ff00"))); t.int(x.index_of(bytes("ff00")));
t.bool(x.contains("no")); t.int(x.index_of("no"));
t.hex(x.at(1)); t.hex(x.join(bytes("00")));
x.set(1, "x").add("last"); t.hex(x.at(1)); t.int(x.len());
t.int(x.clear().add("again").len()); t.hex(x.at(0));
