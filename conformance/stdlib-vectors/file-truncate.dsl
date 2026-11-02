let p = test_temp_dir() + "/truncate";
file_write(p, bytes("000102030405"));
file_write(p, bytes("ff00"));
t.hex(file_read(p));
