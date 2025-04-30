vle      tmp,A(x)      "tmp[0:7] = A[x:x+7]"       % addr=0 stride=32 N=4
vfmul.s  t0,tmp,t5     "t0[0:7] = tmp[0:7] * t5[0:7]"

vle      tmp,A(x)      "tmp[0:7] = A[x:x+7]"       % addr=0 stride=32 N=4
vfmul.s  t1,tmp,t3     "t1[0:7] = tmp[0:7] * t3[0:7]"

vle      tmp,B(x)      "tmp[0:7] = B[x:x+7]"       % addr=128 stride=32 N=4
vfmadd.s t0,tmp,t4,t0  "t0[0:7] = t0[0:7] + tmp[0:7] * t4[0:7]"

vle      tmp,B(x)      "tmp[0:7] = B[x:x+7]"       % addr=128 stride=32 N=4
vfmadd.s t1,tmp,t2,t1  "t1[0:7] = t1[0:7] + tmp[0:7] * t2[0:7]"

vfmul.s  t0,t1,t0      "t0[0:7] = t1[0:7] * t0[0:7]" 

vse      t0,C(x)       "C[x:x+7] = t0[0:7]"        % addr=256 stride=32 N=4

addi    x,x,8           " x = x + 8 "
sub     c,x,X           " c = x != X"
bne     zero,c,label    "if c go back"
