let sum = 0.0;
for (f in range(0, int(3.9))) { for (a in range(0, 2)) { sum = sum + lerp(float(a), float(a + 2), ease(float(f) / 2.0)); } }
t.float(sum);
