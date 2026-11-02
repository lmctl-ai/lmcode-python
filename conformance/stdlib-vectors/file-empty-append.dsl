let p = test_temp_dir() + "/new-empty.bin";
t.bool(file_exists(p));
file_append(p, "");
t.bool(file_exists(p)); t.int(str_len(file_read(p)));
file_append(p, bytes("00ff")); t.hex(file_read(p));
file_write(p, ""); t.int(str_len(file_read(p)));
file_append(p, "a"); t.hex(file_read(p));
