fld    tmp1,A(i)      "tmp1 = A[i]"         % addr=0 stride=16 N=50
fld    tmp2,A(i)      "tmp2 = A[i+1]"       % addr=8 stride=16 N=50
fmul.d tmp2,tmp2,x    "tmp2 = tmp2 * x"
fadd.d tmp1,tmp1,tmp2 "tmp1 = tmp1 + tmp2" 
fmul.d tmp1,tmp1,xpwr "tmp1 = tmp1 * xpwr"
fadd.d res,res,tmp1   "res = res + tmp1" 

fmul.d xpwr,xpwr,x2   "xpwr = xpwr * x2"

addi   i,i,2          " i = i + 2 "
sub    c,i,N          " c = N!=i"
bne    zero,c,label   "if c go back"
