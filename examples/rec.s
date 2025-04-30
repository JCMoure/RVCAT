fmul.d t1,Vi,Z035   "t1 = Vi * Z035"
fmul.d t2,Vi,Z025   "t2 = Vi * Z025"
fsub.d t2,t2,Z060   "t2 = t2 - Z060" 
fld    Wi,W(i)      "Wi = W[i]"       % addr=0 stride=8 N=25
addi   i,i,1        "i  = i + 1"
fmul.d t2,t2,Wi     "t2 = t2 * Wi"
fadd.d Vi,t1,t2     "Vi = t1 + t2"
fsd    Vi,V(i)      "V[i] = Vi"     % addr=1008 stride=8 N=25
sub    c,i,N        "c  = N!=i"
bne    zero,c,label "if c go back"
