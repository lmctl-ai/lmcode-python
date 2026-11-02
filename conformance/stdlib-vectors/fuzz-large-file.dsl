let path = test_temp_dir() + "/large.bin"; let chunk = str_repeat(bytes("00ff0a"), 400001); file_write(path, chunk); file_append(path, bytes("ff00"));
t.int(str_len(file_read(path)));
t.hex(str_substr(file_read(path), 1200000, 5) + bytes("00"));
let lines = file_lines(path);
t.int(lines.len());
t.hex(lines.at(400001) + bytes("00"));
file_write(path, "");
t.int(str_len(file_read(path)));
