fld    Vi,V(i)      "Vi = V[i]"       % addr=0    stride=8 N=25
fld    Wj,W(j)      "Wj = W[j]"       % addr=1000 stride=8 N=25
fmul.d t1,Vi,Z035   "t1 = Vi * Z035"
fmul.d t2,Vi,Z025   "t2 = Vi * Z025"
fsub.d t2,t2,Z06    "t2 = t2 - Z06" 
fmul.d t2,t2,Wj     "t2 = t2 * Wj"
fadd.d Vi,t1,t2     "Vi = t1 + t2"
fsd    Vi,V(i)      "V[i] = Vi"       % addr=0    stride=8 N=25
addi   j,j,1        " j = j + 1 "
addi   i,i,1        " i = i + 1 "
sub    c,i,N        " c = N!=i"
bne    zero,c,label "if c go back"
