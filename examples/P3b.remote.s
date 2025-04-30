fld     t0,A(x)   "t0 = A[x]" % addr=0 stride=4 N=100

fmul.s  t3,t7,t1  "t3 = t7 * t1"
fmul.s  t1,t5,t1  "t1 = t5 * t1"

fmul.s  t2,t8,t0  "t2 = t8 * t0"
fmul.s  t0,t6,t0  "t0 = t6 * t0"

fadd.s  t2,t3,t2  "t2 = t3 + t2"
fadd.s  t0,t1,t0  "t0 = t1 + t0"
 
fmul.s  t0,t0,t2  "t0 = t0 * t2"
fmul.s  t1,t4,t0  "t1 = t4 * t0"

fsw     t1,B(x)   "B[x+1] = t1" % addr=400 stride=4 N=100

addi    x,x,1           " x = x + 1 "
sub     c,x,X           " c = x != X"
bne     zero,c,label    "if c go back"

