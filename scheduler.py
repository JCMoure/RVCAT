from copy        import copy
import json

from .window      import Window, InstrState
from .program     import Program
from .processor   import Processor, _processor
from .instruction import Instruction

from . import exec_graph as ex

global _scheduler

class Scheduler:

    def __init__(self, processor: Processor) -> None:
        self.processor = processor


    def load_program(self, program: Program, iterations: int=3, window_size: int=100) -> None:

        self.program  = program
        self.processor.reset()

        self.iterations = iterations
        self.window_size= window_size
        self.window     = Window(window_size)
        self.n          = iterations*self.program.n
        self.pc         = 0
        self.cycles     = 0

        self.DepEdges   = program.dependence_edges


    def next_cycle(self) -> int:

        xw    = self.processor.stages["execute"]
        rw    = self.processor.stages["retire"]
        sched = self.processor.sched != "greedy"

        issue_queue = {}
        used_ports  = {port:False for port in self.processor.ports}
        MM_access   = -1

        for window_idx in range(self.window.count):

            instr       = self.window[window_idx]
            static_idx  = instr.s_idx
            dynamic_idx = instr.d_idx

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

            elif instr.state == InstrState.EXECUTE:
                instr.latency -= 1
                if instr.latency == 0:
                    #if instr.substate == InstrState.NONE and instr.memory != MemType.NONE:
                        # Memory instruction: Cache access
                    #    mType = 0 if instr.memory == MemType.LOAD else 1
                    #    instr.latency, result, MM_access = self.processor.cache_access(mType, instr.memAddr, self.cycles)
                    #    instr.exec_lat += instr.latency   # add extra latency in case of cache miss
                    
                    #if instr.latency > 0:
                    #    if result == 1:
                    #        instr.substate = InstrState.WAIT_CACHE_MISS
                    #    else:
                    #        instr.substate = InstrState.WAIT_CACHE_2ND
                    #else:
                        instr.state    = InstrState.WRITE_BACK
                        instr.substate = InstrState.NONE

            elif instr.state == InstrState.DISPATCH:

                if instr.substate in [InstrState.NONE, InstrState.WAIT_DATA]:
                    # need to check data dependencies
                    instr.substate = InstrState.NONE
                  
                    for dependence_offset in self.DepEdges[static_idx]:
                        instr_dep = self.window.get_instr( dynamic_idx - dependence_offset )
                        if not instr_dep: # instruction is no longer in the window
                            continue
                        else:
                            if instr_dep.state not in [InstrState.WRITE_BACK, InstrState.RETIRE]:
                                instr.substate = InstrState.WAIT_DATA
                                break

                if instr.substate != InstrState.WAIT_DATA:
                    instr_type     = self.program[static_idx].type
                    resource       = self.processor.get_resource(instr_type)
                    latency, ports = resource
                    if not sched:  # Greedy scheduling algorithm
                      if xw:
                        for port in ports:
                            if not used_ports[port]:
                                used_ports[port] = True
                                instr.exec_cycle = self.cycles
                                instr.latency    = latency
                                instr.exec_lat  += latency
                                instr.state      = InstrState.EXECUTE
                                instr.substate   = InstrState.NONE
                                instr.port_used  = port
                                xw -= 1
                                break
                        if instr.state == InstrState.DISPATCH:
                            instr.substate  = InstrState.WAIT_RESOURCE
                            instr.exec_lat += 1
                      else:
                        instr.substate  = InstrState.WAIT_BANDWIDTH
                        instr.exec_lat += 1

                    else:   # Optimal scheduling: first priority is age, second is using most ports
                      issue_queue[window_idx] = ports
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
                      used_ports[port] = True
                      instr.exec_cycle = self.cycles
                      instr.state      = InstrState.EXECUTE
                      instr.exec_lat  += instr.latency
                      xw -= 1
                  else:
                      instr.substate  = InstrState.WAIT_RESOURCE
                      instr.exec_lat += 1
              else:
                  instr.substate  = InstrState.WAIT_BANDWIDTH
                  instr.exec_lat += 1

        retires = self.processor.stages["retire"] - rw
        return retires, used_ports, MM_access



    def dispatch(self):
        dw = self.processor.stages["dispatch"]
        while dw and not self.window.is_full():
            static_idx = self.pc % self.program.n
            # instr      = self.program[static_idx]
            # if self.processor.cache != None: 
            #     instr_mem = instr.memory
            #     addr      = instr.nextaddr
            #     if instr_mem != MemType.NONE:
            #         instr.nextaddr = addr + instr.stride
            #         instr.count +=1
            #         if instr.count == instr.N:
            #             instr.count = 0
            #             instr.nextaddr = instr.addr
            #     else:
            #         addr = -1
            # else:
            #    instr_mem = MemType.NONE
            #    addr      = -1
            # self.window.push(self.cycles, self.pc, static_idx, instr_mem, addr)
            self.window.push(self.cycles, self.pc, static_idx, "", 0)
            self.pc += 1
            dw      -= 1

        self.cycles += 1


    def generate_timeline_state ( self, dynamic_idx, stages, critical_path):
        
        # Decode Stage
        decode_stage = stages[0].value + ' '
        stages.pop(0)
        if len(critical_path) > 0:
          node = critical_path[-1]
          idx  = node[0] // 3
          stage= node[0] % 3
          if idx == dynamic_idx and stage == 0:
              if node[1] == 1:
                   decode_stage = "\033[91m" + decode_stage + "\033[0m"
              critical_path.pop(-1)

        while stages[0] == InstrState.WAIT_DATA:
            decode_stage += stages[0].value + ' '
            stages.pop(0)
        
        # Execute Stage
        execute_stage = ""
        count = 0

        if len(critical_path) > 0:
          node = critical_path[-1]
          idx  = node[0] // 3
          stage= node[0] % 3
          if idx == dynamic_idx and stage == 1:
              count = node[1]
              execute_stage = "\033[91m"
              critical_path.pop(-1)
        
        while stages[0] != InstrState.RETIRE:
            execute_stage += stages[0].value + ' '
            stages.pop(0)
            count = count-1
            if count == 0:
                execute_stage += "\033[0m"
        
        # Retire Stage
        retire_stage = "R "
        if len(critical_path) > 0:
          node = critical_path[-1]
          idx  = node[0] // 3
          stage= node[0] % 3
          if idx == dynamic_idx and stage == 2:
              critical_path.pop(-1)
              if node[1] == 1:
                   retire_stage = "\033[91m" + "R "+ "\033[0m"

        return decode_stage + execute_stage + retire_stage


    def generate_timeline(self):

        rw = self.processor.stages["retire"]

        timeline      = {i:[] for i in range(self.n + self.window.size + rw)}
        port_timeline = {port:[] for port in self.processor.ports}
        MM_timeline   = []
        INSTR_Info    = []
        ExecGraph     = ex.generate_execution_graph( self.program, self.n, self.window_size, self.DepEdges )

        retired         = 0
        self.cycles     = 0
        last_ret_cycle  = 0
        last_disp_cycle = 0

        while retired < self.n:
            retires, used_ports, MM_access = self.next_cycle()

            if MM_access >= 0:
                MM_timeline.append(MM_access+1)

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

                INSTR_Info.append([r_instr.exec_cycle, r_instr.port_used, r_instr.memAddr])

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
                else:
                    timeline[instr.d_idx].append((self.cycles, instr.state))

        critical_path = ex.longest_path(ExecGraph)

        return timeline, port_timeline, MM_timeline, INSTR_Info, critical_path


    def compute_results( self, usage, cycles_per_iter, name ):
        out = ""

        if usage >= 0.98:
           out += f"\033[96m"

        v1_str = f"{100*usage:0.2f}"
        v2_str = f"{usage*cycles_per_iter:0.2f}"
        out += f"  {name:^10}:\t{v1_str:^10}\t{v2_str:^12}\n"

        if usage >= 0.98:
           out += f"\033[0m"

        return out


    def format_analysis(self) -> str:
        retired         = 0
        self.cycles     = 0
        last_ret_cycle  = 0
        last_disp_cycle = 0

        ports      = self.processor.ports
        port_usage = {port:0 for port in ports}

        ExecGraph  = ex.generate_execution_graph( self.program, self.n, self.window_size, self.DepEdges )

        while retired < self.n:
            retires, used_ports, _ = self.next_cycle()

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

                retired += 1
                if retired >= self.n:
                    break

            self.window.pop(retires)
            self.dispatch()

        critical_path = ex.longest_path(ExecGraph)

        cycles_per_iter = self.cycles / self.iterations
        IPC             = self.n / self.cycles

        out  = f"**** Performance Results ****\n\n"
        out += f"Total Iterations= {self.iterations}, "
        out += f"Total Instructions= {self.n}, "
        out += f"Total cycles= {self.cycles}, "
        out += f"IPC= {IPC:0.2f}\n\n"
        value1_str = f"{cycles_per_iter:0.2f}"
 
        out += f"  Resource  \t Usage(%) \t Cycles/iter.\n"
        out += f"  --------- \t----------\t ------------\n"
        out += f"   PROGRAM  :\t          \t{value1_str:^12}\n"

        dw_usage = IPC / self.processor.stages["dispatch"]
        xw_usage = IPC / self.processor.stages["execute"]
        rw_usage = IPC / self.processor.stages["retire"]

        out += self.compute_results( dw_usage, cycles_per_iter, "dispatch")
        out += self.compute_results( xw_usage, cycles_per_iter, "execute" )
        out += self.compute_results( rw_usage, cycles_per_iter,  "retire" )

        for port in ports:
           usage = port_usage[port]/self.cycles
           name  = f"Port {port}"
           out += self.compute_results( usage, cycles_per_iter, name)

        if self.processor.cache != None:
           MM_usage, MM_Rd_usage, RdMisses, WrMisses = self.processor.cache.statistics(self.cycles)
           out += self.compute_results( MM_usage, cycles_per_iter, "MM total BW")
           out += self.compute_results( MM_Rd_usage, cycles_per_iter, "MM read BW")

           v_str = f"{RdMisses/self.iterations:0.2f}"
           out  += f"   Read Misses:\t          \t {v_str:^10}\n"

           v_str = f"{WrMisses/self.iterations:0.2f}"
           out  += f"  Write Misses:\t          \t {v_str:^10}\n"

        out += f"\n  Critical Path\n  -------------\n"
        out += ex.critical_path_statistics(self.program, critical_path)

        return out


    def format_timeline(self, niters: int = 3):

        global_n = self.n
        self.n = niters * self.program.n

        timeline, _, MM_timeline, INSTR_Info, critical_path = self.generate_timeline()
        pad_iteration = len(str(self.iterations))
        pad_i         = len(str(self.program.n))
        pad           = pad_iteration + pad_i + 5

        out_cycles = f"{' '*pad}{' '.join([str(c_i%10) for c_i in range(self.cycles)])}\n"

        port_timeline = {}
        for port in self.processor.ports:
            port_timeline[port] = [False for i in range(self.cycles)]

        Cycle = 0
        usage = "  "
        for use_time in MM_timeline:
            if use_time >= self.cycles:
                break
            usage += "  "*(use_time-Cycle-1)+"# "
            Cycle = use_time

        name = "MM"
        out_MM = f"{name:{pad_iteration+pad_i+2}} {usage}\n"

        out_timeline = ""
        pad_list = []
        for i, cycles in timeline.items():
            if not cycles or i >= self.n:
                break
            iteration  = i // self.program.n
            i_mod      = i % self.program.n
            if i_mod == 0:
              pad_list.append([cycles[0][0],0])

            pad_list[iteration][1] = cycles[0][0] + len(cycles)

        for i, cycles in timeline.items():
            if not cycles or i >= self.n:
                break
            iteration = i // self.program.n
            i_mod     = i % self.program.n
            init_pad  = pad_list[iteration][0] - 1
            if init_pad < 0:
              init_pad  = 0
            medium_pad= cycles[0][0]-init_pad
            end_pad   = pad_list[iteration][1] - len(cycles) - (init_pad+medium_pad)

            stages = self.generate_timeline_state( i, [s for _,s in cycles], critical_path)

            out_timeline += f"{'  '*init_pad}[{iteration:{pad_iteration}},{i_mod:{pad_i}}]{'  '*medium_pad}"
            out_timeline += f"{stages}{'  '*end_pad}     "
            out_timeline += f"{self.program.instr_str(i_mod)}"
            out_timeline += f" (P.{INSTR_Info[i][1]})"

            port_timeline[ INSTR_Info[i][1] ][ INSTR_Info[i][0] ] = True

            if iteration == 0:
                 out_timeline += f" {self.program.instr_type_str(i_mod)}"

            if INSTR_Info[i][2] >= 0:
                 out_timeline += f" [Addr= {INSTR_Info[i][2]}]"

            out_timeline   += "\n"

        out_Ports = ""
        for port, cycles in port_timeline.items():
            usage = " ".join(["X" if used else " " for used in cycles])
            out_Ports += f"P.{port:{pad_iteration+pad_i+2}} {usage}\n"

        self.n = global_n

        return out_cycles + out_Ports + out_MM + "\n" + out_cycles + out_timeline



    def format_timeline2(self, niters: int = 3) -> str:

        global_n = self.n
        self.n = niters * self.program.n

        timeline, port_timeline, MM_timeline, INSTR_Info, critical_path = self.generate_timeline()
        pad_iteration = len(str(self.iterations))
        pad_i         = len(str(self.program.n))
        pad           = pad_iteration + pad_i + 5

        out = f"{' '*pad}{' '.join([str(c_i%10) for c_i in range(self.cycles)])}\n"
        for port, cycles in port_timeline.items():
            usage = " ".join(["X" if used else " " for used in cycles])
            out += f"P.{port:{pad_iteration+pad_i+2}} {usage}\n"

        Cycle = 0
        usage = "  "
        for use_time in MM_timeline:
            if use_time >= self.cycles:
                break
            usage += "  "*(use_time-Cycle-1)+"# "
            Cycle = use_time

        name = "MM"
        out += f"{name:{pad_iteration+pad_i+2}} {usage}\n"

        out += f"\n{' '*pad}{' '.join([str(c_i%10) for c_i in range(self.cycles)])}\n"

        pad_list = []
        for i, cycles in timeline.items():
            if not cycles or i >= self.n:
                break
            iteration  = i // self.program.n
            i_mod      = i % self.program.n
            if i_mod == 0:
              pad_list.append([cycles[0][0],0])
            
            pad_list[iteration][1] = cycles[0][0] + len(cycles)

        for i, cycles in timeline.items():
            if not cycles or i >= self.n:
                break
            iteration = i // self.program.n
            i_mod     = i % self.program.n
            init_pad  = pad_list[iteration][0] - 1
            if init_pad < 0:
              init_pad  = 0
            medium_pad= cycles[0][0]-init_pad
            end_pad   = pad_list[iteration][1] - len(cycles) - (init_pad+medium_pad)

            stages = self.generate_timeline_state( i, [s for _,s in cycles], critical_path)

            out += f"{'  '*init_pad}[{iteration:{pad_iteration}},{i_mod:{pad_i}}]{'  '*medium_pad}"
            out += f"{stages}{'  '*end_pad}     "
            out += f"{self.program.instr_str(i_mod)}"
            out += f" ({INSTR_Info[i][3]})"

            if iteration == 0:
                 out += f" {self.program.instr_type_str(i_mod)}"

            if INSTR_Info[i][4] >= 0:
                 out += f" [Addr= {INSTR_Info[i][4]}]"

            out   += "\n"

        self.n = global_n

        return out


    def format_analysis_json(self) -> str:
        retired         = 0
        self.cycles     = 0
        last_ret_cycle  = 0
        last_disp_cycle = 0

        ports      = self.processor.ports
        port_usage = {port:0 for port in ports}

        ExecGraph  = ex.generate_execution_graph( self.program, self.n, self.window_size, self.DepEdges )

        while retired < self.n:
            retires, used_ports, _ = self.next_cycle()

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

                retired += 1
                if retired >= self.n:
                    break

            self.window.pop(retires)
            self.dispatch()

        critical_path = ex.longest_path(ExecGraph)

        cycles_per_iter = self.cycles / self.iterations
        IPC             = self.n / self.cycles

        out = {}

        out["total_iterations"] = self.iterations
        out["total_instructions"] = self.n
        out["total_cycles"] = self.cycles
        out["ipc"] = IPC
        out["cycles_per_iteration"] = cycles_per_iter

        out["ports"] = {}
        for port in ports:
           usage = port_usage[port]/self.cycles
           out["ports"][str(port)] = usage*100

        if self.processor.cache != None:
            MM_usage, MM_Rd_usage, RdMisses, WrMisses = self.processor.cache.statistics(self.cycles)
            out["MM_usage"] = MM_usage
            out["MM_read_usage"] = MM_Rd_usage
            out["read_misses"] = RdMisses
            out["write_misses"] = WrMisses

        out["critical_path"] = ex.critical_path_statistics_json(self.program, critical_path)
        return json.dumps(out)

_scheduler = Scheduler(_processor)
