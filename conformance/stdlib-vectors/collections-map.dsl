let m = str_map(); t.int(m.len());
m.set("a", "one").set(bytes("ff00"), bytes("00ff")).set("c", "three");
t.int(m.len()); t.bool(m.has(bytes("ff00"))); t.bool(m.has("missing"));
t.hex(m.get(bytes("ff00"))); t.hex(m.get_or("missing", bytes("fe00")));
t.hex(m.get_or("a", "unused")); m.set("a", "updated");
t.hex(m.key_at(0)); t.hex(m.get("a")); t.int(m.len());
t.bool(m.remove("missing")); t.bool(m.remove("a")); t.hex(m.key_at(0)); t.hex(m.key_at(1));
m.set("a", "tail"); t.hex(m.key_at(2)); t.int(m.clear().set("z", "last").len()); t.hex(m.key_at(0));
