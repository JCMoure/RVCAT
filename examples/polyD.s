fld    tmp,A(i)           "tmp = A[i]"       % addr=0 stride=8 N=25
fmul.d tmp,tmp,xpwr       "tmp = tmp * xpwr"
fadd.d res,res,tmp        "res = res + tmp" 
fmul.d xpwr,xpwr,x        "xpwr = xpwr * x"
addi   i,i,1              "i = i + 1"
sub    c,i,N		  "c = i != N"
bne    zero,c,label       "if c go back"
