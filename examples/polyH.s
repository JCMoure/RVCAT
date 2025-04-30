fld    tmp,A(i)     "tmp = A[i]"       % addr=1000 stride=-8 N=25
fmul.d res,res,x    "res = res * x"
fadd.d res,res,tmp  "res = res + tmp"
sub    i,i,1        "i = i - 1 "
sub    c,i,zero     "c = i < 0"
bne    zero,c,label "if c go back"
