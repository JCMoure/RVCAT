flw    tmp,V(i)      "tmp = V[i]"       % addr=0    stride=4 N=100
flw    tmp2,W(i)     "tmp2= W[i]"       % addr=1000 stride=4 N=100
fadd.s tmp,tmp,tmp2  "tmp = tmp + tmp2" 
fadd.s sum,sum,tmp   "sum = sum + tmp" 
addi   i,i,1         " i = i + 1 "
sub    c,i,N         " c = N!=i"
bne    zero,c,label  "if c go back"
