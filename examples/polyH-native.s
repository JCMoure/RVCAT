fld     tmp,A(i)    	"tmp = A[i]"            % addr=1000 stride=-8 N=25
fmadd.d res,res,x,tmp	"res = res * x + tmp"
sub     i,i,1           "i = i - 1 "
sub     c,i,0           "c = i < 0"
bne     zero,c,label    "if c go back"
