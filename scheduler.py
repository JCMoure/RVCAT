from .window   import Window, InstrState
from .program  import Process, _program
from .cache    import Cache
from .         import exec_graph as ex
import json

global _scheduler

class Scheduler:

    def __init__(self) -> None:
        self.iterations = 0
        self.window_size= 1
        self.dispWidth  = 1
        self.retrWidth  = 1
        self.sched      = "optimal"
        self.nBlocks    = 1
        self.blkSize    = 1
        self.mPenalty   = 0
        self.mIssueTime = 0
        self.nFillBuffers = 2
        self.nWriteBuffers = 2
        self.rThru = 1
        self.port_mask  = 0
        self.n_ports    = 0
        self.cache      = None
        self.window     = Window(1)
        self.num_instr  = 0
        self.n          = 0
        self.dispatched = 0
        self.pc         = 0
        self.cycles     = 0
        self.DepEdges   = []

    def next_cycle(self) -> int:

        xw    = self.n_ports
        rw    = self.retrWidth
        sched = self.sched != "greedy"

        issue_queue = {}
        used_ports  = {port:False for port in range(32) if (self.port_mask >> port) & 1}
        ReadMisses  = []
        SecondMisses= []
        WriteMisses = []
        MMupdates   = []
        if self.cache is not None:
            MMupdates.extend(self.cache.advance(self.cycles))

        for window_idx in range(self.window.count):

            instr       = self.window[window_idx]
            static_idx  = instr.s_idx
            dynamic_idx = instr.d_idx
            instr.waiting_for = None
            instr.waiting_ports = []

            if instr.state == InstrState.WRITE_BACK:
                if rw:
                    if window_idx == 0 or self.window[window_idx-1].state == InstrState.RETIRE:
                        instr.state    = InstrState.RETIRE
                        instr.substate = InstrState.NONE
                        rw -= 1
                    else:
                        instr.substate = InstrState.WAIT_RETIRE
                else:
                    instr.substate = InstrState.WAIT_RETIRE

            elif instr.state == InstrState.LOAD or instr.state == InstrState.STORE:
                if self.cache is None:
                    instr.latency -= 1
                    if instr.latency <= 0:
                        instr.state = InstrState.WRITE_BACK
                        instr.substate = InstrState.NONE
                elif instr.substate in (
                    InstrState.WAIT_MM_REQUEST,
                    InstrState.WAIT_MM_READY,
                    InstrState.WAIT_DATA_READY,
                    InstrState.WAIT_CACHE_2ND,
                    InstrState.WAIT_RETURN_QUEUE,
                ):
                    request_state = self.cache.get_request_state(dynamic_idx)
                    if request_state == "returned":
                        self.cache.consume_completion(dynamic_idx)
                        instr.state = InstrState.WRITE_BACK
                        instr.substate = InstrState.NONE
                    elif request_state == "return_queue":
                        instr.substate = InstrState.WAIT_RETURN_QUEUE
                        instr.exec_lat += 1
                    elif request_state in (
                        "queued_fill",
                        "queued_line",
                        "queued_write",
                        "waiting_mm",
                    ):
                        instr.substate = InstrState.WAIT_MM_REQUEST
                        instr.exec_lat += 1
                    elif request_state == "waiting_writeback":
                        instr.substate = InstrState.WAIT_MM_READY
                        instr.exec_lat += 1
                    else:
                        instr.substate = InstrState.WAIT_DATA_READY
                        instr.exec_lat += 1
                else:
                    instr.latency -= 1
                    if instr.latency <= 0:
                        result = self.cache.request_access(
                            instr.memory - 1,
                            instr.memAddr,
                            self.cycles,
                            dynamic_idx,
                        )
                        if result == "hit":
                            instr.state = InstrState.WRITE_BACK
                            instr.substate = InstrState.NONE
                        else:
                            if instr.memory == 1:
                                ReadMisses.append(dynamic_idx)
                            else:
                                WriteMisses.append(dynamic_idx)
                            if result in ("merged", "secondary"):
                                SecondMisses.append(dynamic_idx)
                            instr.substate = (
                                InstrState.WAIT_CACHE_2ND
                                if result == "secondary"
                                else InstrState.WAIT_MM_REQUEST
                            )

            elif instr.state == InstrState.EXECUTE:
                instr.latency -= 1
                if instr.latency == 0:
                    instr.state    = InstrState.WRITE_BACK
                    instr.substate = InstrState.NONE

            elif instr.state == InstrState.DISPATCH:
                if instr.substate in [InstrState.NONE, InstrState.WAIT_DATA]:
                    instr.substate = InstrState.NONE
                    instr.waiting_for = []
                  
                    for dependence_offset in self.DepEdges[static_idx]:
                        instr_dep = self.window.get_instr( dynamic_idx - dependence_offset )
                        if not instr_dep: # instruction is no longer in the window
                            continue
                        else:
                            if instr_dep.state not in [InstrState.WRITE_BACK, InstrState.RETIRE]:
                                instr.substate = InstrState.WAIT_DATA
                                if instr_dep.d_idx not in instr.waiting_for:
                                    instr.waiting_for.append(instr_dep.d_idx)

                if instr.substate != InstrState.WAIT_DATA:
                    port_mask = _program.instruction_list[static_idx].ports
                    latency   = _program.instruction_list[static_idx].latency
                    required_ports= [port for port in range(32) if (port_mask >> port) & 1]
                    if not sched:  # Greedy scheduling algorithm
                      if xw:
                        for port in required_ports:
                            if not used_ports[port]:
                                used_ports[port] = True
                                instr.exec_cycle = self.cycles
                                instr.latency    = latency
                                instr.exec_lat  += latency
                                if instr.memory > 0:
                                    instr.state = InstrState.LOAD if instr.memory == 1 else InstrState.STORE
                                else:
                                    instr.state = InstrState.EXECUTE
                                instr.substate   = InstrState.NONE
                                instr.port_used  = port
                                instr.port_uses.append((self.cycles, port))
                                xw -= 1
                                break
                        if instr.state == InstrState.DISPATCH:
                            instr.substate  = InstrState.WAIT_RESOURCE
                            instr.waiting_ports = [
                                port for port in required_ports if used_ports[port]
                            ] or required_ports
                            instr.exec_lat += 1
                      else:
                        instr.substate  = InstrState.WAIT_BANDWIDTH
                        instr.exec_lat += 1

                    else:   # Optimal scheduling: first priority is age, second is using most ports
                      issue_queue[window_idx] = required_ports
                      instr.latency           = latency

            elif instr.state != InstrState.RETIRE:
                print("ERROR")


        if sched:  # Improved scheduling algorithm
            issd_isps = ex.old_priority(issue_queue)
            for w_idx in issue_queue:
                instr          = self.window[w_idx]
                instr.substate = InstrState.NONE
                if xw:
                    if w_idx in issd_isps:
                        port             = issd_isps[w_idx]
                        instr.port_used  = port
                        instr.port_uses.append((self.cycles, port))
                        used_ports[port] = True
                        instr.exec_cycle = self.cycles
                        if instr.memory > 0:
                            instr.state = InstrState.LOAD if instr.memory == 1 else InstrState.STORE
                        else:
                            instr.state = InstrState.EXECUTE
                        instr.exec_lat += instr.latency
                        xw -= 1
                    else:
                        instr.substate = InstrState.WAIT_RESOURCE
                        instr.waiting_ports = [
                            port for port in issue_queue[w_idx] if used_ports[port]
                        ] or issue_queue[w_idx]
                        instr.exec_lat += 1
                else:
                    instr.substate = InstrState.WAIT_BANDWIDTH
                    instr.exec_lat += 1

        if self.cache is not None:
            MMupdates.extend(self.cache.advance(self.cycles))

        retires = self.retrWidth - rw
        return retires, used_ports, ReadMisses, SecondMisses, WriteMisses, MMupdates

    def dispatch(self):
        dw = self.dispWidth
        while self.dispatched < self.n and dw and not self.window.is_full():
            static_idx = self.pc % self.num_instr
            instr_mem  = 0
            addr       = -1
            instr      = _program[static_idx]
            if instr.type == "MEM" or instr.type == "VMEM":
                instr_mem  = 1 if instr.oper == "LOAD" else 2
                addr       = instr.addr
                instr.addr = addr + instr.byte_stride
    
            self.window.push(self.cycles, self.pc, static_idx, instr_mem, addr)
            self.pc += 1
            dw      -= 1
            self.dispatched +=1

        self.cycles += 1

    def generate_timeline_state ( self, dynamic_idx, stages, critical_path):
        
        criticalList = []

        # Decode Stage
        decode_stage = "D"
        stages.pop(0)

        if len(critical_path) > 0:
          node = critical_path[-1]
          idx  = node[0] // 3
          stage= node[0] % 3
          if idx == dynamic_idx and stage == 0:
            if node[1] == 1:
                criticalList.append(0)  # Decode stage is in critical path
            critical_path.pop(-1)

        cycle = 1
        while stages[0] == InstrState.WAIT_DATA:
            decode_stage += stages[0].value
            stages.pop(0)
            cycle = cycle+1
        
        # Execute Stage
        execute_stage = ""
        count = 0

        if len(critical_path) > 0:
          node = critical_path[-1]
          idx  = node[0] // 3
          stage= node[0] % 3
          if idx == dynamic_idx and stage == 1:
            count = node[1]-1
            criticalList.append(cycle)  # Execute stage is in critical path
            critical_path.pop(-1)
        
        while stages[0] != InstrState.RETIRE:
            execute_stage += stages[0].value
            stages.pop(0)
            cycle = cycle+1
            if count > 0:
                count = count-1
                criticalList.append(cycle)  # Execute stage is in critical path
        
        # Retire Stage
        retire_stage = "R"
        if len(critical_path) > 0:
          node = critical_path[-1]
          idx  = node[0] // 3
          stage= node[0] % 3
          if idx == dynamic_idx and stage == 2:
              critical_path.pop(-1)
              if node[1] == 1:
                criticalList.append(cycle)  # Execute stage is in critical path

        return (decode_stage + execute_stage + retire_stage, criticalList)

    def generate_timeline(self, ports):
        rw              = self.retrWidth
        retired         = 0
        self.dispatched = 0
        self.cycles     = 0
        last_ret_cycle  = 0
        last_disp_cycle = 0

        timeline      = {i:[] for i in range(self.n + self.window.size + rw)}
        port_timeline = {port:[] for port in ports}
        cache_states = []
        self.fill_buffer_snapshots = []
        self.write_buffer_snapshots = []
        last_cache_state = None
        INSTR_Info    = []
        self.wait_details = []

        ExecGraph     = ex.generate_execution_graph( self.num_instr, self.n, self.window_size, self.DepEdges )

        while retired < self.n:
            retires, used_ports, _,_,_,_ = self.next_cycle()

            if self.cache is not None:
                cache_cycle = self.cycles
                cache_state = self.cache.get_state(cache_cycle)
                cache_signature = tuple(
                    (line["valid"], line["address"], line["dirty"], line["lru"],
                     line["ready_cycle"], line["loading"])
                    for line in cache_state
                )
                if cache_signature != last_cache_state:
                    cache_states.append({
                        "cycle": cache_cycle,
                        "lines": cache_state,
                    })
                    last_cache_state = cache_signature
                buffer_state = self.cache.get_buffer_state()
                self.fill_buffer_snapshots.append({
                    "cycle": cache_cycle,
                    "slots": buffer_state["fill"],
                })
                self.write_buffer_snapshots.append({
                    "cycle": cache_cycle,
                    "slots": buffer_state["write"],
                })

            for port, used in used_ports.items():
                port_timeline[port].append(used)

            for i in range(retires):
                r_instr     = self.window[i]
                dynamic_idx = r_instr.d_idx
                if dynamic_idx != retired:
                    print("ERROR\n")

                disp_latency    = r_instr.disp_cycle - last_disp_cycle
                last_disp_cycle = r_instr.disp_cycle
                ret_latency     = self.cycles - last_ret_cycle
                last_ret_cycle  = self.cycles
                exec_latency    = r_instr.exec_lat

                INSTR_Info.append([
                    r_instr.exec_cycle,
                    r_instr.port_used,
                    r_instr.memAddr,
                    r_instr.port_uses,
                ])

                timeline[ dynamic_idx ].append((self.cycles, r_instr.state))

                ex.exec_graph_update ( ExecGraph, dynamic_idx, disp_latency, exec_latency, ret_latency ) 

                retired += 1
                if retired >= self.n:
                    break

            self.window.pop(retires)
            self.dispatch()

            for instr in self.window:
                if instr.substate != InstrState.NONE:
                    timeline[instr.d_idx].append((self.cycles, instr.substate))
                    if instr.substate == InstrState.WAIT_DATA:
                        self.wait_details.append({
                            "cycle": self.cycles - 1,
                            "instruction_index": instr.d_idx,
                            "reason": "data",
                            "dependencies": instr.waiting_for,
                        })
                    elif instr.substate == InstrState.WAIT_RESOURCE:
                        self.wait_details.append({
                            "cycle": self.cycles - 1,
                            "instruction_index": instr.d_idx,
                            "reason": "ports",
                            "ports": instr.waiting_ports,
                        })
                    elif instr.substate == InstrState.WAIT_BANDWIDTH:
                        self.wait_details.append({
                            "cycle": self.cycles - 1,
                            "instruction_index": instr.d_idx,
                            "reason": "issue-bandwidth",
                        })
                    elif instr.state in (InstrState.LOAD, InstrState.STORE) and \
                            instr.substate in (
                                InstrState.WAIT_MM_REQUEST,
                                InstrState.WAIT_MM_READY,
                                InstrState.WAIT_DATA_READY,
                                InstrState.WAIT_CACHE_2ND,
                            ):
                        self.wait_details.append({
                            "cycle": self.cycles - 1,
                            "instruction_index": instr.d_idx,
                            "reason": "cache",
                            "block_address": (
                                instr.memAddr // self.blkSize
                            ) * self.blkSize,
                            "buffer_state": self.cache.get_request_state(instr.d_idx),
                        })
                    elif instr.substate == InstrState.WAIT_RETURN_QUEUE:
                        self.wait_details.append({
                            "cycle": self.cycles - 1,
                            "instruction_index": instr.d_idx,
                            "reason": "cache-return",
                            "block_address": (
                                instr.memAddr // self.blkSize
                            ) * self.blkSize,
                        })
                else:
                    timeline[instr.d_idx].append((self.cycles, instr.state))

        critical_path = ex.longest_path(ExecGraph)

        return timeline, port_timeline, INSTR_Info, critical_path, ExecGraph, cache_states

    def get_timeline(self, processJSON, niters: int = 3, nret=None) -> str:

        if nret is not None and (isinstance(nret, bool) or not isinstance(nret, int) or nret < 1):
            raise ValueError("nret must be a positive integer.")

        process = Process.from_json(processJSON)
        _program.load_instruction_list(process.instruction_list)

        self.iterations = niters
        self.window_size= process.ROBsize
        self.window     = Window(process.ROBsize)
        self.DepEdges   = _program.dependence_edges
        self.dispWidth  = process.dispatch
        self.retrWidth  = process.retire
        self.mPenalty   = process.mPenalty
        self.mIssueTime = process.mIssueTime
        self.nFillBuffers = process.nFillBuffers
        self.nWriteBuffers = process.nWriteBuffers
        self.rThru = process.rThru
        self.sched      = process.sched
        self.blkSize    = process.blkSize
        self.nBlocks    = process.nBlocks

        _program.assign_memory_addresses(process.Nloop)
        
        # Always creat a new cache object to reset cache state, even if nBlocks is 0 (no cache)
        if self.nBlocks > 0:
            self.cache  = Cache(
                self.nBlocks, self.blkSize, self.mPenalty, self.mIssueTime,
                record_requests=True,
                fill_buffer_count=self.nFillBuffers,
                write_buffer_count=self.nWriteBuffers,
                return_throughput=self.rThru,
            )
        else:
            self.cache = None
            
        self.num_instr  = _program.n
        self.n          = nret if nret is not None else niters*self.num_instr
        self.pc         = 0
        self.cycles     = 0
        self.dispatched = 0

        all_ports = 0
        for instr in _program.instruction_list:
            all_ports |= instr.ports
        self.port_mask = all_ports

        # list of used ports and number of used ports
        ports        = [i for i in range(32) if (all_ports >> i) & 1]
        self.n_ports = len(ports)

        timeline, port_timeline, INSTR_Info, critical_path, ExecGraph, cache_states = self.generate_timeline(ports)

        instructions = []    # List of timeline.instructions

        for i, cycles in timeline.items():

            if not cycles or i >= self.n:
                break

            stages, criticalList = self.generate_timeline_state( i, [s for _,s in cycles], critical_path)

            instr = [
                i // self.num_instr,   # loop iteration
                i % self.num_instr,    # instruction Index
                cycles[0][0]-1,        # starting cycle
                INSTR_Info[i][1],      # port
                stages,                # states
                criticalList,          # critical states
                INSTR_Info[i][2]       # memory address
            ]
            instructions.append(instr)   # insert new instruction in timeline structure

        timelineJson                 = {}
        timelineJson["cycles"]       = self.cycles
        timelineJson["instructions"] = instructions
        timelineJson["arrays"]       = _program.arrays
        timelineJson["critical_path_graph"] = ex.serialize_execution_graph(ExecGraph, self.n)
        timelineJson["wait_details"] = self.wait_details
        timelineJson["resource_usage"] = {
            "ports": port_timeline,
            "port_owners": {
                str(port): [[] for _ in range(self.cycles)]
                for port in ports
            },
        }
        for instruction_index, info in enumerate(INSTR_Info):
            for cycle, port in info[3]:
                timelineJson["resource_usage"]["port_owners"][str(port)][cycle].append(
                    instruction_index
                )
        if self.cache is not None:
            mm_usage = [False] * self.cycles
            for request in self.cache.MEM_requests:
                request_start = request["cycle"]
                for cycle in range(request_start, request_start + self.mIssueTime):
                    if 0 <= cycle < self.cycles:
                        mm_usage[cycle] = True
            timelineJson["resource_usage"]["mm"] = mm_usage
            timelineJson["resource_usage"]["mm_requests"] = self.cache.MEM_requests
            timelineJson["resource_usage"]["cache_state"] = {
                "line_count": self.cache.CACHE_SIZE,
                "snapshots": cache_states,
            }
            timelineJson["resource_usage"]["fill_buffers"] = {
                "capacity": self.cache.FILL_BUFFER_COUNT,
                "snapshots": self.fill_buffer_snapshots,
            }
            timelineJson["resource_usage"]["write_buffers"] = {
                "capacity": self.cache.WRITE_BUFFER_COUNT,
                "snapshots": self.write_buffer_snapshots,
            }

        return json.dumps(timelineJson)

    def get_results(self, processJSON, niters: int = 3) -> str:

        process = Process.from_json(processJSON)
        _program.load_instruction_list(process.instruction_list)

        self.iterations = niters
        self.window_size= process.ROBsize
        self.window     = Window(process.ROBsize)
        self.DepEdges   = _program.dependence_edges
        self.dispWidth  = process.dispatch
        self.retrWidth  = process.retire
        self.mPenalty   = process.mPenalty
        self.mIssueTime = process.mIssueTime
        self.nFillBuffers = process.nFillBuffers
        self.nWriteBuffers = process.nWriteBuffers
        self.rThru = process.rThru
        self.sched      = process.sched
        self.blkSize    = process.blkSize
        self.nBlocks    = process.nBlocks

        _program.assign_memory_addresses(process.Nloop)
        
        if self.nBlocks > 0:
            self.cache  = Cache(
                self.nBlocks,
                self.blkSize,
                self.mPenalty,
                self.mIssueTime,
                record_requests=True,
                fill_buffer_count=self.nFillBuffers,
                write_buffer_count=self.nWriteBuffers,
                return_throughput=self.rThru,
            )
        else:
            self.cache = None

        self.num_instr  = _program.n
        self.n          = niters*self.num_instr
        self.pc         = 0
        self.cycles     = 0
        self.dispatched = 0

        retired         = 0
        last_ret_cycle  = 0
        last_disp_cycle = 0
        Reads, Writes = 0, 0
        RdMisses, WrMisses, S2Misses = 0, 0, 0
        RdPrimaryMisses, RdSecondaryMisses = 0, 0
        WrPrimaryMisses, WrSecondaryMisses = 0, 0

        all_ports = 0
        for instr in _program.instruction_list:
            all_ports |= instr.ports
        self.port_mask = all_ports

        # list of used ports and number of used ports
        ports        = [i for i in range(32) if (all_ports >> i) & 1]
        self.n_ports = len(ports)
        port_usage   = {port:0 for port in ports}

        ExecGraph  = ex.generate_execution_graph( self.num_instr, self.n, self.window_size, self.DepEdges )

        while retired < self.n:
            retires, used_ports, ReadMisses, SecondMisses, WriteMisses, MMupdates = self.next_cycle()
            secondary_misses = set(SecondMisses)

            for idx in ReadMisses:
                if idx < self.n:
                    RdMisses += 1
                    if idx in secondary_misses:
                        RdSecondaryMisses += 1
                    else:
                        RdPrimaryMisses += 1

            for idx in WriteMisses:
                if idx < self.n:
                    WrMisses += 1
                    if idx in secondary_misses:
                        WrSecondaryMisses += 1
                    else:
                        WrPrimaryMisses += 1

            for idx in SecondMisses:
                if idx < self.n:
                    S2Misses += 1

            for port in ports:
                if used_ports[port]:
                   port_usage[port] += 1

            for i in range(retires):
                r_instr     = self.window[i]
                dynamic_idx = r_instr.d_idx
                if dynamic_idx != retired:
                    print("ERROR\n")

                disp_latency    = r_instr.disp_cycle - last_disp_cycle
                last_disp_cycle = r_instr.disp_cycle
                ret_latency     = self.cycles - last_ret_cycle
                last_ret_cycle  = self.cycles
                exec_latency    = r_instr.exec_lat
                ex.exec_graph_update ( ExecGraph, dynamic_idx, disp_latency, exec_latency, ret_latency )

                if r_instr.memory != 0:  # LOAD or STORE
                    if r_instr.memory == 1:  # LOAD
                        Reads += 1
                    elif r_instr.memory == 2:  # STORE
                        Writes += 1

                retired += 1
                if retired >= self.n:
                    break

            self.window.pop(retires)
            self.dispatch()

        critical_path   = ex.longest_path(ExecGraph)
        cycles_per_iter = self.cycles / self.iterations
        IPC             = self.n      / self.cycles

        out = {}
        out["total_iterations"]     = self.iterations
        out["total_instructions"]   = self.n
        out["total_cycles"]         = self.cycles
        out["ipc"]                  = IPC
        out["cycles_per_iteration"] = cycles_per_iter
        out["ports"] = {}
        for port in ports:
           usage = port_usage[port]/self.cycles
           out["ports"][str(port)] = usage*100

        mm_requests = self.cache.MEM_requests if self.cache is not None else []
        mm_reads = sum(request["operation"] != "write" for request in mm_requests)
        mm_writes = sum(request["operation"] == "write" for request in mm_requests)
        mm_busy_cycles = {
            cycle
            for request in mm_requests
            for cycle in range(request["cycle"], request["cycle"] + request["duration"])
            if 0 <= cycle < self.cycles
        }

        out["reads"]          = Reads
        out["read_misses"]    = RdMisses
        out["read_primary_misses"] = RdPrimaryMisses
        out["read_secondary_misses"] = RdSecondaryMisses
        out["writes"]         = Writes
        out["write_misses"]   = WrMisses
        out["write_primary_misses"] = WrPrimaryMisses
        out["write_secondary_misses"] = WrSecondaryMisses
        out["second_misses"]  = S2Misses
        out["MM_Reads"]       = mm_reads
        out["MM_Writes"]      = mm_writes
        out["MM_usage_percent"] = 100 * len(mm_busy_cycles) / self.cycles

        out["critical_path"]   = ex.critical_path_statistics_json(
            self.num_instr, _program.instruction_list, critical_path, self.iterations
        )
        return json.dumps(out)

_scheduler = Scheduler()
