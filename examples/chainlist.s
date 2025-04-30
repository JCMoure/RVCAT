flw    t,V(List)         "t = List->V"        % addr=0 stride=16 N=25
fadd.d Sum,Sum,t         "Sum = Sum + t"
lw     List,next(List)   "List = List->next"  % addr=8 stride=16 N=25
and    c,List,List       "c = List != 0"
bne    zero,c,label     "if c go back"
