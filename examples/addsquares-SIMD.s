vle      t4,V(0)      "t4[0:3] = V[0:3]"       % addr=0 stride=4 N=100
addi     V,V,4        " V = V + 4 "
sub      c,V,EndPtr   " c = V != EndPtr"
vfmul.s  t0,t4,t4     "t0[0:3] = t4[0:3] * t4[0:3]"
vfadd.s  Sv,t0,Sv     "Sv[0:3] = t0[0:3] + Sv[0:3]" 
bne      zero,c,label "if c go back"
