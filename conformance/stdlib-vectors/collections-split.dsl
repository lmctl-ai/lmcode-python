let a = str_split("a,,b,", ","); t.int(a.len()); for (s in a) { t.hex(s); }
let b = str_split("", ","); t.int(b.len()); t.hex(b.at(0));
let c = str_split("aaaaa", "aa"); t.int(c.len()); for (s in c) { t.hex(s); }
let d = str_split(bytes("ff0061ff00"), bytes("ff00")); t.int(d.len()); for (s in d) { t.hex(s); }
t.hex(str_split("é", bytes("c3")).join("!"));
t.hex(str_split("abc", "longer").at(0));
