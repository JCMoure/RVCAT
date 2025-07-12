import csv
from typing import Optional

import importlib.resources

ISA_PATH = importlib.resources.files("rvcat").joinpath("isas")

global _isa

class ISA:

    def __init__(self) -> None:
        self.isas = {}
        self.instructions = {}


    def load_isa(self, name: str) -> None:
        instrs = {}
        file = f"{ISA_PATH}/{name}.csv"
        with open(file, "r") as f:
            lines = csv.DictReader(f, skipinitialspace=True)
            instrs.update({l["mnemonic"]:l for l in lines})
        self.instructions.update(instrs)
        self.isas[name] = list(instrs.keys())


    def info(self, mnemonic: str) -> Optional[dict]:
        return self.instructions.get(mnemonic.upper())


    def help(self, mnemonic: str) -> str:
        info = self.info(mnemonic)
        if info == None:
            return f"No info for {mnemonic} avaliable"
        desc = info.get("description")
        fmt = info.get("format")
        typ = info.get("type")
        action = info.get("action").format(rd="rd", rs1="rs1", rs2="rs2",
                                           rs3="rs3", imm="imm")
        return f"{mnemonic} ({fmt} | {typ}): {desc}\n\t{action}"


    def __repr__(self) -> str:
        out = ""
        for name, instrs in self.isas.items():
            out += f"{name}:\n"
            out += ", ".join(instrs)
            out += "\n"
        return out


_isa = ISA()
