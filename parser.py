from .lexer import Lexer, Token, TokenType

class Label:
    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f"{self.name}"

class Directive:
    def __init__(self, name: str, arguments: str) -> None:
        self.name = name
        self.arguments = arguments

    def __repr__(self) -> str:
        return f"{self.name} {self.arguments}"

class Comment:
    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f"{self.name}"

class Annotation:
    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f"{self.name}"

class Mnemonic:
    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f"{self.name}"

class Description:
    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f"{self.name}"

class Operands:
    def __init__(self, name: list) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f"{self.name}"


class Parser:
    def __init__(self) -> None:
        self.tokens       = []
        self.program_list = []
        self.idx           = 0


    def read_tokens(self, text: str) -> None:
        lexer = Lexer(text)
        self.tokens = []
        self.idx = 0
        while (tk := lexer.next_token()).type != TokenType.EOF:
            self.tokens.append(tk)


    def advance(self, n: int=1) -> None:
        self.idx += n


    def advance_to(self, tk_type: TokenType) -> None:
        while self.tokens[self.idx] != tk_type:
            self.idx += 1


    def advance_after(self, tk_type: TokenType) -> None:
        self.advance_to(tk_type)
        self.advance()


    def retreat_to(self, tk_type: TokenType) -> None:
        while self.tokens[self.idx] != tk_type:
            self.idx += 1
    

    def peek(self, offset: int=0) -> Token:
        i = self.idx + offset
        if 0 <= i and i < len(self.tokens):
            return self.tokens[i]
        else:
            return None


    def peek_n(self, offset: int=0, n: int=1) -> Token:
        i = self.idx + offset + n - 1 
        if 0 < i and i < len(self.tokens):
            return self.tokens[i:i+n]
        else:
            return None


    def peek_match(self, offset: int=0, *tk_types: tuple) -> bool:
        for i, tk_type in enumerate(tk_types):
            if self.peek(i+offset) != tk_type:
                return False
        return True
        

    def parse_label(self) -> Label:
        name = self.peek().value
        if self.peek(-1) == TokenType.DOT:
            name = "."+name
        return Label(name)


    def parse_directive(self) -> Directive:
        name = "." + self.peek().value
        arguments = ""
        while not self.peek_match(1, TokenType.LF):
            arguments += " " + self.peek(1).value
            self.advance()
        return Directive(name, arguments)


    def parse_comment(self) -> Comment:
        name = self.peek().value
        while not self.peek_match(1, TokenType.LF):
            name += " " + self.peek(1).value
            self.advance()
        return Comment(name)


    def parse_annotation(self) -> Comment:
        name = [self.peek().value]
        while not self.peek_match(1, TokenType.LF):
            name.append(self.peek(1).value)
            self.advance()
        return Annotation(name)


    def parse_description(self, tk_type) -> Description:
        name = ""
        while not self.peek_match(1, tk_type):
            if self.peek(1) == TokenType.SYMBOL or self.peek(0) == TokenType.SYMBOL:
                name += " "
            name += self.peek(1).value
            self.advance()
        self.advance()
        return Description(name)


    def parse(self, text: str) -> list:
        self.read_tokens(text)
        program = []

        while self.peek():
            if self.peek() == TokenType.HASH:
                self.advance()
                program.append(self.parse_comment())

            elif self.peek() == TokenType.PERCENT:
                self.advance()
                program.append(self.parse_annotation())

            elif self.peek() == TokenType.STR1:
                program.append(self.parse_description(TokenType.STR1))

            elif self.peek() == TokenType.STR2:
                program.append(self.parse_description(TokenType.STR2))
            
            elif self.peek() == TokenType.SYMBOL:

                if self.peek(1) == TokenType.COLON:
                    program.append(self.parse_label())

                elif self.peek(-1) == TokenType.DOT:
                    program.append(self.parse_directive())

                else:
                    mnemonic = self.peek().value
                    operands = []

                    while self.peek_match(1, TokenType.DOT, TokenType.SYMBOL):
                      value = self.peek(1) + self.peek(2)
                      if self.peek(3) != TokenType.LF:
                         mnemonic += value
                      else:
                         operands.append(value)
                      self.advance(2)

                    while self.peek_match(1, TokenType.SYMBOL, TokenType.COMMA):
                       operands.append(self.peek(1).value)
                       self.advance(2)

                    dot = ""
                    if self.peek(1) == TokenType.DOT:
                      dot = "."
                      self.advance()

                    if self.peek_match(1, TokenType.SYMBOL):
                      operands.append(dot+self.peek(1).value)

                    self.advance()
        
                    program.append( Mnemonic(mnemonic) )
                    program.append( Operands(operands) ) 

            self.advance()
                
        return program


    def parse_file(self, file: str) -> list:
        with open(file, "r") as f:
            text = f.read()
            return self.parse(text)
