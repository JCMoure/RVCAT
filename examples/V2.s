flw    tmp,V(i)      "tmp = V[i]"         % addr=0     stride=8 N=100
fadd.s sum,sum,tmp   "sum = sum + tmp" 
flw    tmp,W(i)      "tmp = W[i]"         % addr=10000 stride=8 N=100
fadd.s sum,sum,tmp   "sum = sum + tmp" 
flw    tmp,V(i)      "tmp = V[i+1]"       % addr=4     stride=8 N=100
fadd.s sum,sum,tmp   "sum = sum + tmp" 
flw    tmp,W(i)      "tmp = W[i+1]"       % addr=10004 stride=8 N=100
fadd.s sum,sum,tmp   "sum = sum + tmp" 
addi   i,i,2         " i = i + 2 "
sub    c,i,N         " c = N!=i"
bne    zero,c,label  "if c go back"
