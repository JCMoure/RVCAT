fmul.s  t2,t6,t0     "t2 = t6 * t0"

flw     t1,A(x)      "t1 = A[x]"    % addr=0 stride=4 N=32
fmul.s  t0,t4,t0     "t0 = t4 * t0"

fmadd.s t2,t5,t1,t2  "t2 = t2 + t5 * t1"
fmadd.s t1,t4,t1,t0  "t1 = t0 + t4 * t1"

fmul.s  t0,t2,t1     "t0 = t2 * t1" 

fsw     t0,B(x)      "B[x+1] = t0"    % addr=132 stride=4 N=32

addi    x,x,1           " x = x + 1 "
sub     c,x,X           " c = x != X"
bne     zero,c,label    "if c go back"
