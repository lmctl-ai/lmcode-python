let p = test_temp_dir() + "/lines";
file_write(p, bytes("610d0a0a"));
let xs = file_lines(p);
t.int(xs.len());
for (s in xs) { t.int(str_len(s)); t.hex(s + bytes("00")); }
let e = test_temp_dir() + "/empty";
file_write(e, "");
t.int(file_lines(e).len());
