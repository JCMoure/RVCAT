fmul.s  t1,t7,t0  "t1 = t7 * t0"

fld     t2,A(x)   "t2 = A[x]" % addr=0 stride=4 N=100

fmul.s  t0,t5,t0  "t0 = t5 * t0"

fmadd.d t1,t6,t2,t1 "t1 = t6 * t2 + t1"
fmadd.d t2,t4,t2,t0 "t2 = t4 * t2 + t0"

fmul.s  t0,t2,t1  "t0 = t2 * t1"
fmul.s  t0,t3,t0  "t0 = t3 * t0"

fsw     t0,B(x)   "B[x+1] = t0" % addr=400 stride=4 N=100

addi    x,x,1           " x = x + 1 "
sub     c,x,X           " c = x != X"
bne     zero,c,label    "if c go back"

