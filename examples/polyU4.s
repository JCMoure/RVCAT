fld    tmp2,A(i)      "tmp2 = A[i+2]"     % addr=16 stride=32 N=25
fld    tmp3,A(i)      "tmp3 = A[i+3]"     % addr=24 stride=32 N=25
fmul.d tmp2,tmp2,x2   "tmp2 = tmp2 * x2"
fmul.d tmp3,tmp3,x3   "tmp3 = tmp3 * x3"
fadd.d tmp2,tmp2,tmp3 "tmp2 = tmp2 + tmp3" 

fld    tmp1,A(i)      "tmp1 = A[i+1]"     % addr=8  stride=32 N=25
fld    tmp0,A(i)      "tmp0 = A[i+0]"     % addr=0  stride=32 N=25
fmul.d tmp1,tmp1,x    "tmp1 = tmp1 * x"
fadd.d tmp0,tmp0,tmp1 "tmp0 = tmp0 + tmp1" 

fadd.d tmp0,tmp0,tmp2 "tmp0 = tmp0 + tmp2" 

fmul.d tmp0,tmp0,xpwr "tmp0 = tmp0 * xpwr"
fmul.d xpwr,xpwr,x4   "xpwr = xpwr * x4"

fadd.d res,res,tmp0   "res = res + tmp0" 

addi   i,i,4          " i = i + 4 "
sub    c,i,N          " c = N!=i"
bne    zero,c,label   "if c go back"
