t.int(str_to_int("+42"));
t.int(str_to_int("-9223372036854775808"));
t.int(str_to_int("9223372036854775808"));
t.int(str_to_int(bytes("3100")));
t.int(str_to_int(" 1"));
