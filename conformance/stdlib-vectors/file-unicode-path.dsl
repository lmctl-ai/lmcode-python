let p = test_temp_dir() + "/résumé 文件-😀.bin";
file_write(p, bytes("00ff0d0a"));
t.bool(file_exists(p)); t.hex(file_read(p));
