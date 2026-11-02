t.bool(str_is_int("9223372036854775807"));
t.bool(str_is_int("-9223372036854775809"));
t.bool(str_is_int("+-1"));
t.bool(str_is_int(bytes("ff")));
t.bool(str_is_int("0x10"));
