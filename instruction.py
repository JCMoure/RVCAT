from enum import Enum
from .isa import _isa
import json


class InstrFormat(Enum):
    REG_REG = "R"       # Register/Register
    REG_REG_4 = "R4"    # Register/Register 4 (+rs3)
    IMM = "I"           # Immediate
    STORE = "S"         # Store
    BRANCH = "B"        # Branch
    UPPER_IMM = "U"     # Upper Immediate
    JUMP = "J"          # Jump
    NONE = ""


class MemType(Enum):
    LOAD   = "L"
    STORE  = "S"
    NONE   = " "


class Instruction:
    def __init__(self, mnemonic: str, operands: list, HLdescription: str, Annotations: list) -> None:
        self.mnemonic = mnemonic
        self.operands = operands
        
        instr_info    = _isa.info(mnemonic)
        self.action   = ""
        self.type     = ""
        self.HLdescrp = HLdescription
        self.LLdescrp = ""
        self.format   = InstrFormat.NONE
        self.rd, self.rs1, self.rs2, self.rs3, self.imm = "", "", "", "", ""

        self.memory  = MemType.NONE
        self.addr    = 0
        self.stride  = 4
        self.N       = 0
        self.nextaddr= 0
        self.count   = 0

        if not instr_info:
            return

        if (fmt := instr_info.get("format"))\
                in ["R", "R4", "I", "S", "B", "U", "J"]:
            self.format = InstrFormat(fmt)

        self.LLdescrp = instr_info.get("description")
        self.type     = instr_info.get("type")

        rd, rs1, rs2, rs3, imm = "", "", "", "", ""

        if self.format == InstrFormat.REG_REG:      # rd, rs1, rs2 / rd, rs1
            if len(self.operands) == 2:
                rd, rs1 = self.operands
            elif len(self.operands) == 3:
                rd, rs1, rs2 = self.operands

        elif self.format == InstrFormat.REG_REG_4:  # rd, rs1, rs2, rs3
            if len(self.operands) == 4:
                rd, rs1, rs2, rs3 = self.operands

        elif self.format == InstrFormat.IMM:        # rd, imm(rs1) / rd, rs1, imm
            if len(self.operands) == 2:
                rd, rs1_imm = self.operands
                imm, rs1 = rs1_imm[:-1].split("(")
            elif len(self.operands) == 3:
                rd, rs1, imm = self.operands

        elif self.format == InstrFormat.STORE:      # rs2, imm(rs1)
            if len(self.operands) == 2:
                rs2, rs1_imm = self.operands
                imm, rs1 = rs1_imm[:-1].split("(")

        elif self.format == InstrFormat.BRANCH:     # rs1, rs2, imm
            if len(self.operands) == 3:
                rs1, rs2, imm = self.operands

        elif self.format == InstrFormat.UPPER_IMM\
                or self.format == InstrFormat.JUMP: # rd, imm
            if len(self.operands) == 2:
                rd, imm = self.operands

        self.rd, self.rs1, self.rs2, self.rs3, self.imm = rd, rs1, rs2, rs3, imm

        action      = instr_info.get("action")
        self.action = action.format(rd=rd, rs1=rs1, rs2=rs2, rs3=rs3, imm=imm)

        main_type = self.type[:self.type.find(".")]
        if main_type.upper() == "MEM":
            mem_type = self.type[4:]
            if mem_type[0] == 'L' or mem_type[1] == 'L':
                self.memory = MemType.LOAD
            else:
                self.memory = MemType.STORE

            indexes = [index for (index, item) in enumerate ( Annotations ) if item == "="]
            for i in indexes:
                if   Annotations[i-1] == "addr":
                    self.addr     = int(Annotations[i+1])
                    self.nextaddr = self.addr
                elif Annotations[i-1] == "stride":
                    self.stride = int(Annotations[i+1])
                elif Annotations[i-1] == "N":
                    self.N      = int(Annotations[i+1])


    def __repr__(self, mode=0) -> str:
        if self.HLdescrp == "" or mode == 0:
          return f"{self.mnemonic:7} {','.join(self.operands): <16}"
        return f"{self.HLdescrp: <16}"
    
    def json(self) -> str:
    
        return {
            "mnemonic":   self.mnemonic,
            "operands":   self.operands,
            "action":     self.action,
            "type":       self.type,
            "HLdescrp":   self.HLdescrp,
            "LLdescrp":   self.LLdescrp,
            "format":     self.format.value,
            "rd":         self.rd,
            "rs1":        self.rs1,
            "rs2":        self.rs2,
            "rs3":        self.rs3,
            "imm":        self.imm,
            "memory":     self.memory.value,
            "addr":       self.addr,
            "stride":     self.stride,
            "N":          self.N,
            "nextaddr":   self.nextaddr,
            "count":      self.count
        }

