#!/usr/bin/env python3
import sys
import re
import os
import json
import argparse
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Union, Optional, Tuple, Any
from enum import Enum, auto
import readline  # For command history

# Define the core query model using dataclasses for clarity
class CommandType(Enum):
    FIND = auto()
    COUNT = auto()
    EXTRACT = auto()

class TargetType(Enum):
    LINES = auto()
    WORDS = auto()

class ConditionType(Enum):
    CONTAINS = auto()
    STARTS_WITH = auto()
    ENDS_WITH = auto()
    MATCHES = auto()  # Regex match
    REPEAT = auto()   # Repeat patterns

class LogicType(Enum):
    AND = auto()
    OR = auto()

@dataclass
class Condition:
    type: ConditionType
    value: str
    negated: bool = False
    logic: LogicType = LogicType.AND
    quantifier: Optional[str] = None  # For repeat conditions

@dataclass
class Modifiers:
    ignore_case: bool = False
    multiline: bool = False
    dotall: bool = False
    whole_word: bool = False
    context_lines: int = 0

@dataclass
class Query:
    command: CommandType = CommandType.FIND
    target: TargetType = TargetType.LINES
    conditions: List[Condition] = field(default_factory=list)
    modifiers: Modifiers = field(default_factory=Modifiers)
    extraction_pattern: Optional[str] = None
    file_pattern: Optional[str] = None
    output_format: str = "text"

# Token-based parser for more reliable parsing
class TokenType(Enum):
    KEYWORD = auto()
    STRING = auto()
    NUMBER = auto()
    OPERATOR = auto()
    IDENTIFIER = auto()
    EOF = auto()

@dataclass
class Token:
    type: TokenType
    value: str
    line: int
    column: int

class Parser:
    """A simple recursive descent parser for our query language"""
    
    KEYWORDS = {
        "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", 
        "LINES", "WORDS", "CONTAINS", "STARTS", "ENDS", "WITH",
        "MATCHES", "IGNORE", "CASE", "WHOLE", "WORD", "EXTRACT",
        "COUNT", "BEFORE", "AFTER", "CONTEXT", "AS", "JSON", "CSV",
        "AT", "LEAST", "MOST", "EXACTLY", "BETWEEN", "TIMES"
    }
    
    def __init__(self, query_text: str):
        self.text = query_text
        self.tokens = self._tokenize(query_text)
        self.pos = 0
        self.current_token = self.tokens[0] if self.tokens else None
        
    def _tokenize(self, text: str) -> List[Token]:
        """Convert query text to a list of tokens"""
        tokens = []
        i = 0
        line = 1
        column = 1
        
        while i < len(text):
            # Skip whitespace
            if text[i].isspace():
                if text[i] == '\n':
                    line += 1
                    column = 1
                else:
                    column += 1
                i += 1
                continue
                
            # Handle quoted strings
            if text[i] in ('"', "'"):
                quote_char = text[i]
                start = i
                i += 1
                while i < len(text) and text[i] != quote_char:
                    if text[i] == '\\' and i + 1 < len(text):
                        i += 2  # Skip escaped character
                    else:
                        i += 1
                if i < len(text):
                    value = text[start+1:i]  # Extract without quotes
                    tokens.append(Token(TokenType.STRING, value, line, column))
                    column += (i - start + 1)
                    i += 1  # Skip closing quote
                else:
                    raise SyntaxError(f"Unterminated string at line {line}, column {column}")
                continue
                
            # Handle numbers
            if text[i].isdigit():
                start = i
                while i < len(text) and text[i].isdigit():
                    i += 1
                value = text[start:i]
                tokens.append(Token(TokenType.NUMBER, value, line, column))
                column += (i - start)
                continue
                
            # Handle keywords and identifiers
            if text[i].isalpha() or text[i] == '_':
                start = i
                while i < len(text) and (text[i].isalnum() or text[i] == '_'):
                    i += 1
                value = text[start:i]
                if value.upper() in self.KEYWORDS:
                    tokens.append(Token(TokenType.KEYWORD, value.upper(), line, column))
                else:
                    tokens.append(Token(TokenType.IDENTIFIER, value, line, column))
                column += (i - start)
                continue
                
            # Handle operators
            if text[i] in "=<>!&|":
                start = i
                while i < len(text) and text[i] in "=<>!&|":
                    i += 1
                value = text[start:i]
                tokens.append(Token(TokenType.OPERATOR, value, line, column))
                column += (i - start)
                continue
                
            # Skip other characters
            i += 1
            column += 1
            
        # Add EOF token
        tokens.append(Token(TokenType.EOF, "", line, column))
        return tokens
    
    def _advance(self):
        """Move to the next token"""
        self.pos += 1
        if self.pos < len(self.tokens):
            self.current_token = self.tokens[self.pos]
        else:
            self.current_token = self.tokens[-1]  # EOF token
            
    def _expect(self, token_type: TokenType, value: str = None) -> Token:
        """Expect a token of a specific type and optionally value"""
        if self.current_token.type != token_type:
            raise SyntaxError(f"Expected {token_type.name}, got {self.current_token.type.name} "
                             f"at line {self.current_token.line}, column {self.current_token.column}")
        if value and self.current_token.value != value:
            raise SyntaxError(f"Expected '{value}', got '{self.current_token.value}' "
                             f"at line {self.current_token.line}, column {self.current_token.column}")
        token = self.current_token
        self._advance()
        return token
    
    def _optional(self, token_type: TokenType, value: str = None) -> Optional[Token]:
        """Optionally consume a token if it matches"""
        if self.current_token.type == token_type and (value is None or self.current_token.value == value):
            token = self.current_token
            self._advance()
            return token
        return None
    
    def parse(self) -> Query:
        """Parse the query and return a Query object"""
        query = Query()
        
        # Parse: SELECT [LINES|WORDS|COUNT|EXTRACT "pattern"]
        self._expect(TokenType.KEYWORD, "SELECT")
        
        # Check for COUNT or EXTRACT
        if self._optional(TokenType.KEYWORD, "COUNT"):
            query.command = CommandType.COUNT
        elif self._optional(TokenType.KEYWORD, "EXTRACT"):
            query.command = CommandType.EXTRACT
            # Get the extraction pattern
            pattern_token = self._expect(TokenType.STRING)
            query.extraction_pattern = pattern_token.value
        
        # Parse target type (LINES or WORDS)
        if self._optional(TokenType.KEYWORD, "LINES"):
            query.target = TargetType.LINES
        elif self._optional(TokenType.KEYWORD, "WORDS"):
            query.target = TargetType.WORDS
        else:
            # Default to LINES if not specified
            query.target = TargetType.LINES
            
        # Parse: FROM [filename]
        self._expect(TokenType.KEYWORD, "FROM")
        file_token = self._expect(TokenType.STRING) if self.current_token.type == TokenType.STRING else None
        if file_token:
            query.file_pattern = file_token.value
            
        # Parse: WHERE condition
        if self._optional(TokenType.KEYWORD, "WHERE"):
            query.conditions = self._parse_conditions()
            
        # Parse modifiers
        self._parse_modifiers(query)
            
        # Parse output format
        if self._optional(TokenType.KEYWORD, "AS"):
            if self._optional(TokenType.KEYWORD, "JSON"):
                query.output_format = "json"
            elif self._optional(TokenType.KEYWORD, "CSV"):
                query.output_format = "csv"
                
        return query
        
    def _parse_conditions(self) -> List[Condition]:
        """Parse WHERE clause conditions"""
        conditions = []
        
        # Parse first condition
        condition = self._parse_condition()
        conditions.append(condition)
        
        # Parse any additional conditions with AND/OR
        while self.current_token.type == TokenType.KEYWORD and self.current_token.value in ("AND", "OR"):
            logic = LogicType.AND if self.current_token.value == "AND" else LogicType.OR
            self._advance()
            
            # Handle NOT keyword
            negated = False
            if self._optional(TokenType.KEYWORD, "NOT"):
                negated = True
                
            next_condition = self._parse_condition()
            next_condition.logic = logic
            next_condition.negated = negated
            conditions.append(next_condition)
            
        return conditions
        
    def _parse_condition(self) -> Condition:
        """Parse a single condition"""
        # Default
        condition_type = ConditionType.CONTAINS
        
        # Check for specific condition types
        if self._optional(TokenType.KEYWORD, "CONTAINS"):
            condition_type = ConditionType.CONTAINS
        elif self._optional(TokenType.KEYWORD, "STARTS"):
            self._expect(TokenType.KEYWORD, "WITH")
            condition_type = ConditionType.STARTS_WITH
        elif self._optional(TokenType.KEYWORD, "ENDS"):
            self._expect(TokenType.KEYWORD, "WITH")
            condition_type = ConditionType.ENDS_WITH
        elif self._optional(TokenType.KEYWORD, "MATCHES"):
            condition_type = ConditionType.MATCHES
            
        # Parse quantifiers (AT LEAST X TIMES, etc.)
        quantifier = None
        if self._optional(TokenType.KEYWORD, "AT"):
            if self._optional(TokenType.KEYWORD, "LEAST"):
                num = self._expect(TokenType.NUMBER).value
                self._optional(TokenType.KEYWORD, "TIMES")
                quantifier = f"{{{num},}}"
                condition_type = ConditionType.REPEAT
            elif self._optional(TokenType.KEYWORD, "MOST"):
                num = self._expect(TokenType.NUMBER).value
                self._optional(TokenType.KEYWORD, "TIMES")
                quantifier = f"{{0,{num}}}"
                condition_type = ConditionType.REPEAT
        elif self._optional(TokenType.KEYWORD, "EXACTLY"):
            num = self._expect(TokenType.NUMBER).value
            self._optional(TokenType.KEYWORD, "TIMES")
            quantifier = f"{{{num}}}"
            condition_type = ConditionType.REPEAT
        elif self._optional(TokenType.KEYWORD, "BETWEEN"):
            low = self._expect(TokenType.NUMBER).value
            self._expect(TokenType.KEYWORD, "AND")
            high = self._expect(TokenType.NUMBER).value
            self._optional(TokenType.KEYWORD, "TIMES")
            quantifier = f"{{{low},{high}}}"
            condition_type = ConditionType.REPEAT
            
        # Get the value (pattern) for the condition
        value_token = self._expect(TokenType.STRING)
        
        return Condition(
            type=condition_type,
            value=value_token.value,
            quantifier=quantifier
        )
        
    def _parse_modifiers(self, query: Query):
        """Parse query modifiers"""
        while True:
            if self._optional(TokenType.KEYWORD, "IGNORE"):
                if self._optional(TokenType.KEYWORD, "CASE"):
                    query.modifiers.ignore_case = True
                    
            elif self._optional(TokenType.KEYWORD, "WHOLE"):
                if self._optional(TokenType.KEYWORD, "WORD"):
                    query.modifiers.whole_word = True
                    
            elif self._optional(TokenType.KEYWORD, "MULTILINE"):
                query.modifiers.multiline = True
                
            elif self._optional(TokenType.KEYWORD, "DOTALL"):
                query.modifiers.dotall = True
                
            elif self._optional(TokenType.KEYWORD, "CONTEXT"):
                num = self._expect(TokenType.NUMBER).value
                query.modifiers.context_lines = int(num)
                
            else:
                break  # No more modifiers

# Query builder class for constructing the regex patterns
class QueryBuilder:
    @staticmethod
    def build_pattern(query: Query) -> Tuple[str, List[str]]:
        """Build regex patterns from the query"""
        include_parts_and = []
        include_parts_or = []
        exclude_patterns = []
        
        # Process each condition
        for condition in query.conditions:
            pattern = QueryBuilder._build_condition_pattern(condition, query.modifiers)
            
            if condition.negated:
                exclude_patterns.append(pattern)
            else:
                if condition.logic == LogicType.OR:
                    include_parts_or.append(pattern)
                else:
                    include_parts_and.append(pattern)
                    
        # Combine patterns
        if include_parts_and and include_parts_or:
            # Build AND chain
            and_chain = "".join(f"(?=.*{p})" for p in include_parts_and) + ".*"
            # Build OR group
            or_group = "|".join(include_parts_or)
            include_pattern = f"(?:({and_chain})|({or_group}))"
        elif include_parts_and:
            # Only AND conditions
            and_chain = "".join(f"(?=.*{p})" for p in include_parts_and) + ".*"
            include_pattern = and_chain
        elif include_parts_or:
            # Only OR conditions
            or_group = "|".join(include_parts_or)
            include_pattern = f"(?:{or_group})"
        else:
            # No include conditions
            include_pattern = ".*"
            
        # Apply whole word boundaries if needed
        if query.modifiers.whole_word:
            include_pattern = rf"\b(?:{include_pattern})\b"
            exclude_patterns = [rf"\b(?:{p})\b" for p in exclude_patterns]
            
        return include_pattern, exclude_patterns
        
    @staticmethod
    def _build_condition_pattern(condition: Condition, modifiers: Modifiers) -> str:
        """Build regex pattern for a single condition"""
        # Escape the text unless it's a regex pattern
        is_regex = condition.type == ConditionType.MATCHES
        text = condition.value if is_regex else re.escape(condition.value)
        
        if condition.type == ConditionType.STARTS_WITH:
            return f"^{text}"
        elif condition.type == ConditionType.ENDS_WITH:
            return f"{text}$"
        elif condition.type == ConditionType.CONTAINS:
            return text
        elif condition.type == ConditionType.MATCHES:
            return text
        elif condition.type == ConditionType.REPEAT:
            quantifier = condition.quantifier if condition.quantifier else "{1,}"
            return f"(?:{text}){quantifier}"
        else:
            return text  # Default fallback

# Query executor class for processing files against queries
class QueryExecutor:
    @staticmethod
    def execute(query: Query, input_source=None) -> Dict[str, Any]:
        """Execute a query against input text data"""
        # Set up regex flags
        flags = 0
        if query.modifiers.ignore_case:
            flags |= re.IGNORECASE
        if query.modifiers.multiline:
            flags |= re.MULTILINE
        if query.modifiers.dotall:
            flags |= re.DOTALL
            
        # Build the regex patterns
        include_pattern, exclude_patterns = QueryBuilder.build_pattern(query)
        
        # Decide the input source
        if input_source is None:
            if query.file_pattern and query.file_pattern.strip():
                try:
                    input_file = open(query.file_pattern, "r", encoding="utf-8", errors="ignore")
                except FileNotFoundError:
                    return {"error": f"File not found: {query.file_pattern}"}
            else:
                input_file = sys.stdin
        else:
            # Allow passing an already open file-like object
            input_file = input_source
        
        # Process the input
        results = {
            "command": query.command.name,
            "target": query.target.name,
            "matched_count": 0,
            "matched_items": [],
            "extracted_items": []
        }
        
        # Read all lines (for context line support)
        lines = input_file.readlines()
        
        # If the input was a file we opened, close it
        if input_source is None and query.file_pattern and query.file_pattern.strip():
            input_file.close()
            
        # Process lines based on target type
        if query.target == TargetType.WORDS:
            for i, line in enumerate(lines):
                line_stripped = line.rstrip("\n")
                words = line_stripped.split()
                
                for word in words:
                    if QueryExecutor._matches_item(word, include_pattern, exclude_patterns, flags):
                        results["matched_count"] += 1
                        
                        if query.command == CommandType.FIND:
                            results["matched_items"].append({"line": i+1, "content": word})
                            
                        if query.command == CommandType.EXTRACT and query.extraction_pattern:
                            extracted = re.findall(query.extraction_pattern, word, flags=flags)
                            for ex in extracted:
                                if isinstance(ex, tuple):
                                    results["extracted_items"].append(" ".join(ex))
                                else:
                                    results["extracted_items"].append(ex)
        else:  # TargetType.LINES
            for i, line in enumerate(lines):
                line_stripped = line.rstrip("\n")
                
                if QueryExecutor._matches_item(line_stripped, include_pattern, exclude_patterns, flags):
                    results["matched_count"] += 1
                    
                    if query.command in (CommandType.FIND, CommandType.EXTRACT):
                        # Add context lines if specified
                        context_lines = []
                        
                        if query.modifiers.context_lines > 0:
                            # Add before lines
                            start_idx = max(0, i - query.modifiers.context_lines)
                            context_lines.extend([
                                {"line": j+1, "content": lines[j].rstrip("\n"), "type": "before"}
                                for j in range(start_idx, i)
                            ])
                            
                            # Add the matched line
                            context_lines.append({"line": i+1, "content": line_stripped, "type": "match"})
                            
                            # Add after lines
                            end_idx = min(len(lines), i + query.modifiers.context_lines + 1)
                            context_lines.extend([
                                {"line": j+1, "content": lines[j].rstrip("\n"), "type": "after"}
                                for j in range(i+1, end_idx)
                            ])
                            
                            results["matched_items"].append({"line": i+1, "content": line_stripped, "context": context_lines})
                        else:
                            results["matched_items"].append({"line": i+1, "content": line_stripped})
                    
                    if query.command == CommandType.EXTRACT and query.extraction_pattern:
                        extracted = re.findall(query.extraction_pattern, line_stripped, flags=flags)
                        for ex in extracted:
                            if isinstance(ex, tuple):
                                results["extracted_items"].append(" ".join(ex))
                            else:
                                results["extracted_items"].append(ex)
                    
        return results
    
    @staticmethod
    def _matches_item(item: str, include_pattern: str, exclude_patterns: list, flags: int) -> bool:
        """Return True if item matches include_pattern and doesn't match any exclude_pattern"""
        # Check include pattern
        if not re.search(include_pattern, item, flags=flags):
            return False
            
        # Check exclude patterns
        for pattern in exclude_patterns:
            if re.search(pattern, item, flags=flags):
                return False
                
        return True
        
# Output formatter class for different output formats
class OutputFormatter:
    @staticmethod
    def format_results(results: Dict[str, Any], format_type: str) -> str:
        """Format results in the specified format"""
        if format_type == "json":
            return json.dumps(results, indent=2)
        elif format_type == "csv":
            # Basic CSV output
            output = []
            
            # Header
            if results["command"] == "COUNT":
                output.append(f"Target,Count")
                output.append(f"{results['target']},{results['matched_count']}")
            elif results["command"] == "EXTRACT":
                output.append(f"Item")
                for item in results["extracted_items"]:
                    output.append(f"{item}")
            else:  # FIND
                output.append(f"Line,Content")
                for item in results["matched_items"]:
                    output.append(f"{item['line']},\"{item['content'].replace('\"', '\"\"')}\"")
                    
            return "\n".join(output)
        else:  # text (default)
            if results["command"] == "COUNT":
                return f"Matched {results['target'].lower()}: {results['matched_count']}"
            elif results["command"] == "EXTRACT":
                return "\n".join(results["extracted_items"])
            else:  # FIND
                output = []
                for item in results["matched_items"]:
                    if "context" in item:
                        # Add separator before context blocks
                        output.append("\n" + "-" * 40)
                        
                        for ctx_line in item["context"]:
                            prefix = ""
                            if ctx_line["type"] == "before":
                                prefix = "- "
                            elif ctx_line["type"] == "match":
                                prefix = "> "
                            elif ctx_line["type"] == "after":
                                prefix = "+ "
                                
                            output.append(f"{prefix}{ctx_line['line']}: {ctx_line['content']}")
                            
                        # Add separator after context blocks
                        output.append("-" * 40)
                    else:
                        output.append(f"{item['line']}: {item['content']}")
                        
                return "\n".join(output)

# Interactive mode implementation
def interactive_mode():
    """Run the application in interactive mode"""
    examples = [
        "SELECT LINES FROM \"file.txt\" WHERE CONTAINS \"error\"",
        "SELECT COUNT WORDS FROM \"log.txt\" WHERE STARTS WITH \"Exception\" IGNORE CASE",
        "SELECT EXTRACT \"(\\d+)\" FROM \"data.csv\" WHERE CONTAINS \"ID\" CONTEXT 2",
        "SELECT LINES WHERE MATCHES \"\\b\\d{3}-\\d{2}-\\d{4}\\b\" WHOLE WORD"  # Find SSNs
    ]
    
    print("=== TextQuery Interactive Mode ===")
    print("Enter queries or 'help' for assistance, 'exit' to quit.")
    
    history_file = os.path.expanduser("~/.textquery_history")
    try:
        readline.read_history_file(history_file)
    except FileNotFoundError:
        pass
    
    while True:
        try:
            query_text = input("\nQuery> ").strip()
            
            if not query_text:
                continue
                
            if query_text.lower() == "exit":
                break
                
            if query_text.lower() == "help":
                print("\nTextQuery Help:")
                print("  Syntax: SELECT [LINES|WORDS|COUNT|EXTRACT \"pattern\"] FROM \"file\" WHERE [conditions] [modifiers]")
                print("\nExamples:")
                for ex in examples:
                    print(f"  {ex}")
                print("\nConditions:")
                print("  CONTAINS \"text\"           - Line/word contains text")
                print("  STARTS WITH \"text\"        - Line/word starts with text")
                print("  ENDS WITH \"text\"          - Line/word ends with text")
                print("  MATCHES \"regex\"           - Line/word matches regex pattern")
                print("  AT LEAST n TIMES \"text\"   - Text appears at least n times")
                print("\nModifiers:")
                print("  IGNORE CASE                - Case-insensitive matching")
                print("  WHOLE WORD                 - Match whole words only")
                print("  CONTEXT n                  - Show n lines before/after matches")
                print("  AS [JSON|CSV]              - Output format")
                continue
                
            # Parse and execute the query
            try:
                parser = Parser(query_text)
                query = parser.parse()
                
                # If no file specified, use stdin with a prompt
                if not query.file_pattern:
                    print("Enter text (press Ctrl+D when finished):")
                    input_text = sys.stdin.read()
                    from io import StringIO
                    input_source = StringIO(input_text)
                else:
                    input_source = None
                    
                results = QueryExecutor.execute(query, input_source)
                
                if "error" in results:
                    print(f"Error: {results['error']}")
                else:
                    output = OutputFormatter.format_results(results, query.output_format)
                    print("\nResults:")
                    print(output)
                    
            except Exception as e:
                print(f"Error: {str(e)}")
                
        except KeyboardInterrupt:
            print("\nOperation cancelled.")
        except EOFError:
            break
            
    # Save command history
    readline.write_history_file(history_file)
    print("\nExiting TextQuery. Goodbye!")
    
# Command-line interface
def main():
    parser = argparse.ArgumentParser(description="TextQuery - A text processing tool with a SQL-like query language")
    parser.add_argument("-q", "--query", help="Query string in TextQuery language")
    parser.add_argument("-f", "--file", help="Input file to process")
    parser.add_argument("-i", "--interactive", action="store_true", help="Run in interactive mode")
    parser.add_argument("-o", "--output", choices=["text", "json", "csv"], default="text", 
                      help="Output format")
    
    args = parser.parse_args()
    
    if args.interactive:
        interactive_mode()
        return
        
    if args.query:
        try:
            query_parser = Parser(args.query)
            query = query_parser.parse()
            
            # Override file if specified on command line
            if args.file:
                query.file_pattern = args.file
                
            # Override output format if specified
            if args.output:
                query.output_format = args.output
                
            results = QueryExecutor.execute(query)
            
            if "error" in results:
                print(f"Error: {results['error']}", file=sys.stderr)
                sys.exit(1)
                
            output = OutputFormatter.format_results(results, query.output_format)
            print(output)
            
        except Exception as e:
            print(f"Error: {str(e)}", file=sys.stderr)
            sys.exit(1)
    else:
        interactive_mode()

if __name__ == "__main__":
    main()
