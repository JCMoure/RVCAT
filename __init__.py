import numpy as np

from .program   import _program
from .processor import _processor
from .scheduler import _scheduler 

def load_program(program: str) -> None:
        _program.load_program(program)

def load_processor(processor: str) -> None:
        _processor.load_processor(processor)

def show_program_annotated() -> None:
    if _program.loaded:
        print(_program.annotate_action())

def show_program_execution() -> None:
    if _program.loaded:
        print(_program.annotate_execution())

def show_program_performance() -> None:
    if _program.loaded:
        print(_program.show_static_performance_analysis())

def show_program() -> None:
    if _program.loaded:
        print(_program)
