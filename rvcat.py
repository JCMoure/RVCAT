#! /bin/env python3.9
import sys
import argparse
import cmd2

from shell import Shell

def parse_arguments() -> argparse.Namespace:
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("file", nargs="?", help="assembly input file")
    return arg_parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()

    sh = Shell()
    if args.file:
        sh.onecmd(f"load program {args.file}")
    Shell().cmdloop()
