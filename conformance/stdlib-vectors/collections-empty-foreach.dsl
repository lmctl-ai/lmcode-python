for (s in str_list()) { t.hex(s); }
for (i in int_list()) { t.int(i); }
for (f in float_list()) { t.float(f); }
t.int(str_list().len()); t.int(int_list().len()); t.int(float_list().len());
t.hex(str_list().join(","));
