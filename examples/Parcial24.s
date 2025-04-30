fld    T1,V(i)            "T1 = V[i]"       % addr=0 stride=8 N=25
fmul.d T2,L,T1            "T2 = L * T1"
fld    T4,X(i)            "T4 = X[i]"       % addr=10000 stride=8 N=25 
fadd.d T3,T2,T1           "T3 = T2 + T1" 
fadd.d T5,R,T4            "T5 = R + T4" 
fadd.d L,T2,R             "L = T2 + R"
fsd    T5,X(i)            "X[i] = T5"       % addr=10000 stride=8 N=25 
fmul.d R,T3,T5            "R = T3 * T5"

addi   i,i,1              "i = i + 1"
sub    c,i,N              "c = i < N"
bne    zero,c,label       "if c go init"
