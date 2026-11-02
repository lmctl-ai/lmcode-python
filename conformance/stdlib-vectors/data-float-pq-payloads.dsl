let x=float_pq().push(math_sqrt(-1.0),0.0).push(-0.0,1.0); let n=x.pop(); t.bool(n!=n); t.float(x.pop());
