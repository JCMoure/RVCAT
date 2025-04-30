fld    t,V(i)       "t = V[i]"       % addr=0 stride=8 N=40
fadd.d S,S,t        "S = S + t" 
addi   i,i,1        " i = i + 1 "
sub    c,i,N        " c = N!=i"
bne    zero,c,label "if c go back"
