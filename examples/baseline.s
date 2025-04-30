flw    tmp,V(i)      "tmp = V[i]"       % addr=0    stride=4 N=100
fadd.s sum,sum,tmp   "sum = sum + tmp" 
flw    tmp,W(i)      "tmp = W[i]"       % addr=1000 stride=4 N=100
fadd.s sum,sum,tmp   "sum = sum + tmp" 
addi   i,i,1         " i = i + 1 "
sub    c,i,N         " c = N!=i"
bne    zero,c,label  "if c go back"
