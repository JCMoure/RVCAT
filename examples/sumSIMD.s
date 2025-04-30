vle     t,V(i)       "t[0:3] = V[i:i+3]"          % addr=0 stride=32 N=10
vfadd.d S,S,t        "S[0:3] = S[0:3] + t[0:3]"
addi   i,i,4         "i = i + 4"
sub    c,i,N         "c = i!= N"
bne    zero,c,label  "if c go back"
