from math import inf

def old_priority(isps: dict[int,list]) -> dict[tuple[int,int]]:
    _ais = [inf]    # assigned instructions
    _aps = [-1]     # assigned ports
    nis = len(isps) # number of instructions
    isps_is = sorted(isps.keys()) # instructions indexes
    def dfs(n=0, ais=[], aps=[]):
        if n == nis:
            nonlocal _ais, _aps
            if len(ais) >= len(_ais) and sum(ais) < sum(_ais):
                _ais = ais
                _aps = aps
            return

        i = isps_is[n]
        assigned = False
        for p in isps[i]:
            if p not in aps:
                assigned = True
                dfs(n+1, ais+[i], aps+[p])

        if not assigned:
            dfs(n+1, ais, aps)

    dfs()
    return dict(zip(_ais, _aps))
