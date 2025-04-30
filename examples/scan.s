lw    tmp,V(i)      "tmp = V[i+1]"       % addr=0  stride=4 N=100
addi  i,i,1         " i = i + 1 "
add   Vi,Vi,tmp     "Vi = Vi + tmp" 
sw    Vi,V(i)       "V[i+1] = Vi "       % addr=0  stride=4 N=100
bne   n,i,label     "if i<n go back"
