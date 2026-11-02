let blocker = test_temp_dir() + "/blocker";
file_write(blocker, "x");
file_write(blocker + "/child", "x");
