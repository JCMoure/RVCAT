addi   R,T,0              "R = T"
fld    T,A(i)             "T = A[i]"       % addr=0 stride=8 N=25
fsub.d R,R,Two            "R = R - Two"
fadd.d T,T,J              "T = T + J" 
fld    J,B(i)             "J= B[i]"       % addr=10000 stride=8 N=25 
fmul.d J,J,R              "J = J * R"

addi   i,i,1              "i = i + 1"
sub    c,i,N              "c = i != N"
bne    zero,c,label       "if c go back"
