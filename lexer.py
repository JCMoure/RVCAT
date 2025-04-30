from enum import Enum, auto

class TokenType(Enum):
    LF = auto()
    EOF = auto()
    COMMA = auto()
    DOT = auto()
    COLON = auto()
    HASH = auto()
    PERCENT = auto()
    STR1 = auto()
    STR2 = auto()
    SYMBOL = auto()
    UNDEF = auto()

class Token:
    def __init__(self, value: str, type: TokenType) -> None:
        self.value = value
        self.type = type

    def __repr__(self) -> str:
        return f"<{self.type}> {self.value}"

    def __eq__(self, tk_type: TokenType) -> bool:
        return self.type == tk_type

    def __add__(self, other) -> str:
        return self.value + other.value


class Lexer:
    def __init__(self, text: str) -> None:
        self.text = text
        self.idx = 0
    

    def peek(self) -> str:
        if self.idx >= len(self.text):
            return "\0"
        else:
            return self.text[self.idx]


    def advance(self) -> None:
        self.idx += 1


    def next_token(self) -> Token:

        while self.peek().isspace() and self.peek() != "\n":
            self.advance()

        tk_val = self.peek()
        tk_type = TokenType.UNDEF

        # symbol = re.compile("[a-z,A-Z,0-9,-,%,_,.,(,)]")

        if tk_val == "\n":
            tk_type = TokenType.LF
        elif tk_val == "\0":
            tk_type = TokenType.EOF
        elif tk_val == ",":
            tk_type = TokenType.COMMA
        elif tk_val == ".":
            tk_type = TokenType.DOT
        elif tk_val == ":":
            tk_type = TokenType.COLON
        elif tk_val == "#":
            tk_type = TokenType.HASH
        elif tk_val == "%":
            tk_type = TokenType.PERCENT
        elif tk_val == '"':
            tk_type = TokenType.STR1
        elif tk_val == "'":
            tk_type = TokenType.STR2
        elif tk_val.isalnum() or tk_val in ["-", "_", "[", "]", "(", ")"]:
            tk_type = TokenType.SYMBOL
            self.advance()
            while self.peek().isalnum() or self.peek() in ["(", ")", ".", "_", "]", "["]:
                tk_val += self.peek()
                self.advance()

        if tk_type != TokenType.SYMBOL:
            self.advance()

        return Token(tk_val, tk_type)
