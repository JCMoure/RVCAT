import json

class Instruction:
    def __init__(self) -> None:
        self.type     = ""
        self.text     = ""
        self.destin   = ""
        self.source1  = ""
        self.source2  = ""
        self.source3  = ""
        self.constant = ""

    @staticmethod
    def from_json(data: dict):
        instr = Instruction()

        # Override fields explicitly
        instr.type     = data.get("type", "")
        instr.text     = data.get("text", "")
        instr.destin   = data.get("destin", "")
        instr.source1  = data.get("source1", "")
        instr.source2  = data.get("source2", "")
        instr.source3  = data.get("source3", "")
        instr.constant = data.get("constant", "")
        return instr

    def json(self) -> str:
    
        return {
            "type":     self.type,
            "text":     self.text,
            "destin":   self.destin,
            "source1":  self.source1,
            "source2":  self.source2,
            "source3":  self.source3,
            "constant": self.constant
        }

    def __repr__(self) -> str:
        return f"{self.text: <16}"

