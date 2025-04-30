fmadd.d t1,Vi,Z025,Z060	"t1 = Vi * Z025 - Z060"
fld    Wi,W(i)          "Wi = W[i]"       % addr=0 stride=8 N=25
addi   i,i,1            "i  = i + 1"
fmul.d t1,t1,Wi         "t1 = t1 * Wi"
fmadd.d Vi,Vi,Z035,t1	"Vi = Vi * Z035 + t1"
fsd    Vi,V(i)          "V[i] = Vi"     % addr=1008 stride=8 N=25
sub    c,i,N            "c  = N!=i"
bne    zero,c,label     "if c go back"
