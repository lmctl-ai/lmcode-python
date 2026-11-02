let p = test_temp_dir() + "/boundaries";
file_write(p, bytes("0a"));
t.int(file_lines(p).len());
for (s in file_lines(p)) { t.hex(s + bytes("00")); }
file_write(p, bytes("ff000a610d62"));
t.int(file_lines(p).len());
for (s in file_lines(p)) { t.hex(s + bytes("00")); }
