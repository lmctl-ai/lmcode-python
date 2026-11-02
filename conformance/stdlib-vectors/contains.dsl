t.bool(str_contains("", ""));
t.bool(str_contains(bytes("61ff0062"), bytes("ff00")));
t.bool(str_contains("abc", "ac"));
