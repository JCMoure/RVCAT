import os
import argparse
import readline
import cmd2

from program   import _program
from processor import _processor
from scheduler import _scheduler 
from isa       import _isa

class Shell(cmd2.Cmd):
    def __init__(self) -> None:
        super().__init__()
        self.prompt = "> "

    load_parser     = cmd2.Cmd2ArgumentParser()
    load_subparsers = load_parser.add_subparsers(dest="mode")

    program_parser  = load_subparsers.add_parser("program", help="load program")
    program_parser.add_argument("file", help="assembly file")

    processor_parser = load_subparsers.add_parser("processor", help="load processor")
    processor_parser.add_argument("name", help="processor name")

    isa_parser      = load_subparsers.add_parser("isa", help="load isa")
    isa_parser.add_argument("name", help="isa name")

    @cmd2.with_argparser(load_parser)

    def do_load(self, args: str) -> None:
        if args.mode == "program":
            _program.load_program(args.file)

        elif args.mode == "processor":
            _processor.load_processor(args.name)

        elif args.mode == "isa":
            _isa.load_isa(args.name)

    complete_load = cmd2.Cmd.path_complete

    show_parser = cmd2.Cmd2ArgumentParser()
    show_subparsers = show_parser.add_subparsers(dest="mode")

    program_parser = show_subparsers.add_parser("program", help="show program")
    program_parser_group = program_parser.add_mutually_exclusive_group()
    
    program_parser.add_argument("-i", "--iterations", type=int, help="number of iterations")
 
    program_parser_group.add_argument("-d", "--dependencies",
                                      action="store_true",
                                      help="show data dependencies among instructions")

    program_parser_group.add_argument("-a", "--annotated", action="store_true",
                                      help="provide RTL (Register Transfer Language) description of instructions")

    program_parser_group.add_argument("-x", "--execution", action="store_true",
                                      help="provide latency and execution resource needs of instructions")

    program_parser_group.add_argument("-p", "--performance", action="store_true",
                                      help="show static performance analysis")

    program_parser_group.add_argument("-m", "--memory", action="store_true",
                                      help="show memory trace")

    program_parser_group.add_argument("-c", "--critical", action="store_true",
                                      help="show critical path of multiple iterations of the program loop")

    processor_parser = show_subparsers.add_parser("processor", help="show processor")

    isa_parser = show_subparsers.add_parser("isa", help="show working ISA")

    @cmd2.with_argparser(show_parser)
    def do_show(self, args: str) -> None:


        if args.mode == "program":
            if _program.loaded:
                if args.dependencies:
                    self.ppaged(_program.show_dependencies())
                elif args.annotated:
                    self.ppaged(_program.annotate_action())
                elif args.execution:
                    self.ppaged(_program.annotate_execution())
                elif args.performance:
                    self.ppaged(_program.show_static_performance_analysis())
                elif args.memory:
                    self.ppaged(_program.show_memory_trace())
                elif args.critical:
                   if args.iterations:
                      self.ppaged(_program.show_critical_path(args.iterations))
                   else:
                      self.ppaged(_program.show_critical_path(1))
                else:
                    self.ppaged(_program)
        elif args.mode == "processor":
            self.ppaged(_processor)
        elif args.mode == "isa":
            self.ppaged(_isa)


    info_parser = cmd2.Cmd2ArgumentParser()
    info_parser.add_argument("mnemonic", help="instruction mnemonic")

    @cmd2.with_argparser(info_parser)
    def do_info(self, args: str) -> None:
        self.ppaged(_isa.help(args.mnemonic))


    run_parser = cmd2.Cmd2ArgumentParser()

    run_parser.add_argument("-i", "--iterations", type=int,
                                 help="number of iterations")

    run_parser.add_argument("-w", "--window_size", type=int,
                                 help="size of the execution window")

    run_subparsers = run_parser.add_subparsers(dest="mode")

    timeline_parser = run_subparsers.add_parser("timeline",
                                                 help="show execution timeline")

    analysis_parser = run_subparsers.add_parser("analysis",
                                                 help="show execution analysis")

    memtrace_parser = run_subparsers.add_parser("memtrace",
                                                 help="show memory trace")
    @cmd2.with_argparser(run_parser)

    def do_run(self, args: str) -> None:
        if _program.loaded:

            if args.iterations and args.window_size:
                _scheduler.load_program(_program, args.iterations, args.window_size)
            elif args.iterations:
                _scheduler.load_program(_program, iterations=args.iterations)
            elif args.window_size:
                _scheduler.load_program(_program, window_size=args.window_size)
            else:
                _scheduler.load_program(_program)

            if args.mode == "timeline":
                tl = _scheduler.format_timeline()
                self.ppaged(tl)

            elif args.mode == "analysis":
                counters = _scheduler.format_analysis()
                self.ppaged(counters)

            elif args.mode == "memtrace":
                counters = _scheduler.format_memtrace()
                self.ppaged(counters)
