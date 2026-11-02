t.hex(str_substr("é!", 1, 1));
t.hex(str_substr("abc", -2, 99));
t.int(str_len(str_substr("abc", 4, 1)));
t.int(str_len(str_substr("abc", 0, -1)));
t.hex(str_substr(bytes("ff0061"), 0, 2));
