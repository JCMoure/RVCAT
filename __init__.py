import numpy as np

from .program   import _program
from .processor import _processor
from .scheduler import _scheduler 
# from .isa       import _isa

def load_program(program: str) -> None:
        _program.load_program(program)

def load_processor(processor: str) -> None:
        _processor.load_processor(processor)

# def load_isa(isa: str) -> None:
#        _isa.load_isa(isa)

# def show_program_dependencies() -> None:
#    if _program.loaded:
#        print(_program.show_dependencies())

def show_program_annotated() -> None:
    if _program.loaded:
        print(_program.annotate_action())

def show_program_execution() -> None:
    if _program.loaded:
        print(_program.annotate_execution())

def show_program_performance() -> None:
    if _program.loaded:
        print(_program.show_static_performance_analysis())

# def show_program_memory() -> None:
#    if _program.loaded:
#        print(_program.show_memory_trace())

def show_program() -> None:
    if _program.loaded:
        print(_program)

# def show_processor() -> None:
#        print(_processor)

# def show_isa() -> None:
#        print(_isa)
