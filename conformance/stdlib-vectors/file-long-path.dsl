let p = test_long_path();
t.bool(str_len(p) > 260);
file_write(p, bytes("ff0061"));
t.bool(file_exists(p)); t.hex(file_read(p));
