let p = test_temp_dir() + "/large";
let data = str_repeat(bytes("00ff"), 600000);
file_write(p, data);
t.int(str_len(file_read(p)));
t.bool(file_read(p) == data);
file_append(p, bytes("aa"));
t.int(str_len(file_read(p)));
