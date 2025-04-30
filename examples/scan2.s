lw    tmp1,V(i)      "tmp1 = V[i+1]"       % addr=0  stride=8 N=100
lw    tmp2,V(i)      "tmp2 = V[i+2]"       % addr=4  stride=8 N=100
add   tmp,tmp1,Vi    "tmp  = tmp1 + Vi"
sw    tmp,V(i)       "V[i+1] = tmp "       % addr=0  stride=8 N=100

add   tmp1,tmp2,tmp1 "tmp1 = tmp2 + tmp1" 
add   Vi,Vi,tmp1     "Vi = Vi + tmp1" 

sw    Vi,V(i)        "V[i+2] = Vi "        % addr=4  stride=8 N=100

addi  i,i,2          " i = i + 2 "
bne   n,i,label      "if i<n go back"
