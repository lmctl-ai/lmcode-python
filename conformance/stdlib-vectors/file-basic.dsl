let p = test_temp_dir() + "/bytes.bin";
file_write(p, bytes("6100ff"));
t.hex(file_read(p));
t.bool(file_exists(p));
file_append(p, bytes("0a62"));
t.hex(file_read(p));
t.bool(file_exists(test_temp_dir()));
t.bool(file_exists(test_temp_dir() + "/missing"));
