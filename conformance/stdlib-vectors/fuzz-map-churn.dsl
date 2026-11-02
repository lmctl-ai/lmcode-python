let m = str_map(); m.set(bytes("00ff"), "deleted").set("stable", "v"); m.remove(bytes("00ff"));
for (i in range(0, 4096)) { m.set(str(i), "v"); m.remove(str(i)); }
t.int(m.len());
t.bool(m.has(bytes("00ff")));
t.hex(m.key_at(0) + bytes("00"));
m.set("other", bytes("ff00")).set("stable", bytes("00ff"));
t.hex(m.key_at(0) + bytes("00"));
t.hex(m.key_at(1) + bytes("00"));
t.hex(m.get("stable") + bytes("00"));
m.clear(); for (i in range(0, 4096)) { m.set(str(i), "v"); } let good = true;
for (i in range(0, 4096)) { if (i % 2 == 0) { m.remove(str(i)); good = good && m.key_at(m.len() - 1) == "4095"; } }
t.bool(good);
t.int(m.len());
let sum = 0; for (i in range(0, 2048)) { sum = sum + str_to_int(m.key_at(i)); }
t.int(sum);
m.set("0", "reinsert");
t.hex(m.key_at(2048) + bytes("00"));
t.hex(m.key_at(0) + bytes("00"));
