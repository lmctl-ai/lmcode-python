let blocker = test_temp_dir() + "/blocker";
file_write(blocker, "x");
file_append(blocker + "/child", "x");
