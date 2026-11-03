lmcode_return_put("before", "must be discarded");
@case fn fail() -> int implements Entry {
  lmcode_return_put("partial", "must be discarded");
  entry_fail();
  return 7;
}
