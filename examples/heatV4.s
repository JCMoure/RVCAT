flw     t0,IN(x)     "t0 = IN[x+1]"       % addr=8 stride=4 N=100
flw     t1,IN(x)     "t1 = IN[x-1]"       % addr=0 stride=4 N=100
fadd.s  t0,t0,t1     "t0 = t0 + t1" 
fmul.s  t0,t0,H      "t0 = t0 * H" 
flw     t1,IN(x)     "t1 = IN[x]"         % addr=4 stride=4 N=100
fmadd.s t0,t1,C,t0   "t0 = t1 * C + t0"
fsw     t0,OUT(x)    "OUT[x] = t0"        % addr=412 stride=4 N=100
addi    x,x,1        " x = x + 1 "
sub     c,x,N        " c = x<=N"
bne     zero,c,label "if c go back"
