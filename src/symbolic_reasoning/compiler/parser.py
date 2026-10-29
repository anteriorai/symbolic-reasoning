"""A pure Python parser for the SRG policy language."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, ClassVar

from symbolic_reasoning.gen.py.ast import (
    AggregatorDefinition,
    AllExpression,
    AnyExpression,
    AtLeastExpression,
    AtMostExpression,
    CitationDefinition,
    CitationReference,
    CitationRegion,
    Definition,
    ExactlyExpression,
    Expression,
    Location,
    NoneExpression,
    NotExpression,
    OutcomeDefinition,
    OutcomeReference,
    Path,
    PolicyContextDefinition,
    Position,
    PredicateDefinition,
    ReferenceExpression,
    SourceFile,
)

# Tree-sitter lexes these as keywords, so they can never be references.
_OPERATORS = frozenset({"all", "any", "none", "atleast", "atmost", "exactly", "not"})

# JavaScript String.trim(), used by the TypeScript parser for triple quotes.
_STRING_TRIM_CHARACTERS = (
    " \t\n\r\v\f\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005"
    "\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
)


class ParseError(ValueError):
    """Base class for SRG syntax and structural errors."""

    def __init__(self, message: str, loc: Location | None = None) -> None:
        super().__init__(message)
        self.loc = loc


class SRGSyntaxError(ParseError):
    """Raised when source text does not match the SRG grammar."""


class StructuralError(ParseError):
    """Raised when syntactically valid source violates SRG rules."""


@dataclass(frozen=True)
class _Token:
    kind: str
    text: str
    loc: Location


class _Lexer:
    """Tokenize the deliberately small SRG language while retaining locations."""

    _PUNCTUATION: ClassVar[dict[str, str]] = {
        ":": "COLON",
        ",": "COMMA",
        "{": "LBRACE",
        "}": "RBRACE",
        "[": "LBRACKET",
        "]": "RBRACKET",
        "(": "LPAREN",
        ")": "RPAREN",
    }

    def __init__(self, source: str) -> None:
        self.source = source
        self.index = 0
        self.line = 0
        self.column = 0
        self.offset = 0

    def tokenize(self) -> list[_Token]:
        tokens: list[_Token] = []
        while self.index < len(self.source):
            char = self.source[self.index]
            if char in " \t\r\n\v\f\ufeff":
                self._advance()
            elif char == "#":
                self._skip_comment()
            elif self.source.startswith(("=>", "!=>"), self.index):
                start = self._position()
                arrow = "!=>" if self.source.startswith("!=>", self.index) else "=>"
                for _ in arrow:
                    self._advance()
                tokens.append(
                    _Token("ARROW", arrow, Location(start=start, end=self._position()))
                )
            elif char in self._PUNCTUATION:
                start = self._position()
                self._advance()
                tokens.append(
                    _Token(
                        self._PUNCTUATION[char],
                        char,
                        Location(start=start, end=self._position()),
                    )
                )
            elif char == '"':
                tokens.append(self._string())
            elif char.isascii() and (char.isalpha() or char == "_"):
                tokens.append(self._identifier())
            elif char.isascii() and char.isdigit():
                tokens.append(self._number())
            else:
                raise SRGSyntaxError(
                    f"Unexpected character {char!r}",
                    Location(start=self._position(), end=self._position()),
                )

        position = self._position()
        tokens.append(_Token("EOF", "", Location(start=position, end=position)))
        return tokens

    def _position(self) -> Position:
        return Position(line=self.line, column=self.column, offset=self.offset)

    def _advance(self) -> None:
        char = self.source[self.index]
        self.index += 1
        # web-tree-sitter indexes JavaScript strings in UTF-16 code units.
        width = 2 if ord(char) > 0xFFFF else 1
        self.offset += width
        if char == "\n":
            self.line += 1
            self.column = 0
        else:
            self.column += width

    def _skip_comment(self) -> None:
        # A lone carriage return ends a line too, as in the tree-sitter grammar.
        while self.index < len(self.source) and self.source[self.index] not in "\r\n":
            self._advance()

    def _identifier(self) -> _Token:
        start = self._position()
        index = self.index
        self._advance()
        while self.index < len(self.source):
            char = self.source[self.index]
            if not (char.isascii() and (char.isalnum() or char == "_")):
                break
            self._advance()
        return _Token(
            "IDENT",
            self.source[index : self.index],
            Location(start=start, end=self._position()),
        )

    def _number(self) -> _Token:
        start = self._position()
        index = self.index
        while self.index < len(self.source) and self.source[self.index] in "0123456789":
            self._advance()
        if self.index < len(self.source) and self.source[self.index] == ".":
            self._advance()
            if (
                self.index >= len(self.source)
                or self.source[self.index] not in "0123456789"
            ):
                raise SRGSyntaxError(
                    "Invalid number literal",
                    Location(start=start, end=self._position()),
                )
            while (
                self.index < len(self.source)
                and self.source[self.index] in "0123456789"
            ):
                self._advance()
        return _Token(
            "NUMBER",
            self.source[index : self.index],
            Location(start=start, end=self._position()),
        )

    def _string(self) -> _Token:
        start = self._position()
        index = self.index
        delimiter = '"""' if self.source.startswith('"""', self.index) else '"'
        for _ in delimiter:
            self._advance()
        while self.index < len(self.source):
            if self.source.startswith(delimiter, self.index):
                for _ in delimiter:
                    self._advance()
                return _Token(
                    "STRING",
                    self.source[index : self.index],
                    Location(start=start, end=self._position()),
                )
            if self.source[self.index] == "\\":
                self._escape()
            else:
                self._advance()
        raise SRGSyntaxError(
            "Unterminated string", Location(start=start, end=self._position())
        )

    def _escape(self) -> None:
        """Consume an escape allowed by grammar.js, without decoding raw strings."""
        start = self._position()
        self._advance()
        if self.index < len(self.source):
            char = self.source[self.index]
            self._advance()
            if char in "\\'\"nrt":
                return
            if char in "uU":
                digits = 4 if char == "u" else 8
                for _ in range(digits):
                    if (
                        self.index >= len(self.source)
                        or self.source[self.index] not in "0123456789abcdefABCDEF"
                    ):
                        break
                    self._advance()
                else:
                    return
        raise SRGSyntaxError(
            "Invalid escape sequence", Location(start=start, end=self._position())
        )


class _Parser:
    _COMMON_PROPERTIES: ClassVar[set[str]] = {"label", "doc", "cite", "metadata"}

    def __init__(self, source: str) -> None:
        self.tokens = _Lexer(source).tokenize()
        self.index = 0

    def parse(self) -> SourceFile:
        definitions: list[Definition] = []
        while not self._at("EOF"):
            declaration = self._expect("IDENT", "Expected an SRG declaration")
            if declaration.text == "policy_context":
                self._expect("COLON", "Expected ':' after policy_context")
                value = self._string("policy_context requires a string")
                definitions.append(
                    Definition(
                        root=PolicyContextDefinition(
                            type="policy_context_definition",
                            value=value,
                            loc=Location(
                                start=declaration.loc.start,
                                end=self._previous().loc.end,
                            ),
                        )
                    )
                )
            elif declaration.text == "predicate":
                definitions.append(Definition(root=self._predicate(declaration)))
            elif declaration.text == "outcome":
                definitions.append(Definition(root=self._outcome(declaration)))
            elif declaration.text == "define":
                definitions.append(Definition(root=self._aggregator(declaration)))
            elif declaration.text == "citation":
                definitions.append(Definition(root=self._citation(declaration)))
            elif declaration.text == "path":
                definitions.append(Definition(root=self._path(declaration)))
            else:
                raise SRGSyntaxError(
                    f"Unknown declaration {declaration.text!r}", declaration.loc
                )
        return SourceFile(type="source_file", definitions=definitions)

    def _predicate(self, start: _Token) -> PredicateDefinition:
        identifier = self._identifier("Predicate definition missing id")
        self._expect("COLON", "Expected ':' after predicate id")
        question = self._string("Predicate definition missing question")
        properties, context, end = self._properties(
            allow_context=True, end=self._previous()
        )
        return PredicateDefinition(
            type="predicate_definition",
            id=identifier.text,
            question=question,
            context=context,
            loc=Location(start=start.loc.start, end=end.loc.end),
            **properties,
        )

    def _outcome(self, start: _Token) -> OutcomeDefinition:
        identifier = self._identifier("Outcome definition missing id")
        self._expect("COLON", "Expected ':' after outcome id")
        description = self._string("Outcome definition missing description")
        properties, _, end = self._properties(allow_context=False, end=self._previous())
        return OutcomeDefinition(
            type="outcome_definition",
            id=identifier.text,
            description=description,
            loc=Location(start=start.loc.start, end=end.loc.end),
            **properties,
        )

    def _aggregator(self, start: _Token) -> AggregatorDefinition:
        identifier = self._identifier("Aggregator definition missing id")
        self._expect("COLON", "Expected ':' after aggregator id")
        expression = self._expression()
        properties, _, end = self._properties(allow_context=False, end=self._previous())
        return AggregatorDefinition(
            type="aggregator_definition",
            id=identifier.text,
            expression=expression,
            loc=Location(start=start.loc.start, end=end.loc.end),
            **properties,
        )

    def _citation(self, start: _Token) -> CitationDefinition:
        identifier = self._identifier("Citation definition missing id")
        self._expect("COLON", "Expected ':' after citation id")
        values, end = self._property_block()
        source_ref = values.get("source_ref")
        if not source_ref or not isinstance(source_ref, str):
            raise StructuralError(
                f"Citation '{identifier.text}' missing required field: source_ref",
                identifier.loc,
            )
        regions = self._citation_regions(identifier, values.get("regions"))
        known = {"source_ref", "filename", "regions", "excerpt"}
        metadata = {key: value for key, value in values.items() if key not in known}
        return CitationDefinition(
            type="citation_definition",
            id=identifier.text,
            source_ref=source_ref,
            filename=values.get("filename") or None
            if isinstance(values.get("filename"), str)
            else None,
            regions=regions,
            excerpt=values.get("excerpt") or None
            if isinstance(values.get("excerpt"), str)
            else None,
            metadata=metadata or None,
            loc=Location(start=start.loc.start, end=end.loc.end),
        )

    def _path(self, start: _Token) -> Path:
        identifier = self._identifier("Path missing id")
        self._expect("COLON", "Expected ':' after path id")
        steps = [self._expression()]
        arrow = self._expect("ARROW", "Path requires '=>' or '!=>' before its outcome")
        conditions = [arrow.text == "=>"]
        while True:
            candidate = self._expression()
            if self._at("ARROW"):
                conditions.append(self._advance().text == "=>")
                steps.append(candidate)
                continue
            if not isinstance(candidate.root, ReferenceExpression):
                raise SRGSyntaxError(
                    "Path must end with an outcome identifier", candidate.root.loc
                )
            outcome = _Token(
                "IDENT",
                candidate.root.id,
                candidate.root.loc or Location(start=start.loc.end, end=start.loc.end),
            )
            break
        properties, _, end = self._properties(allow_context=False, end=outcome)
        return Path(
            type="path",
            id=identifier.text,
            steps=steps,
            conditions=conditions if not all(conditions) else None,
            outcome_ref=OutcomeReference(id=outcome.text, loc=outcome.loc),
            loc=Location(start=start.loc.start, end=end.loc.end),
            **properties,
        )

    def _properties(
        self, *, allow_context: bool, end: _Token
    ) -> tuple[dict[str, Any], str | None, _Token]:
        result: dict[str, Any] = {}
        context: str | None = None
        seen: set[str] = set()
        allowed = self._COMMON_PROPERTIES | ({"context"} if allow_context else set())
        while self._at("IDENT") and self._peek().text in allowed:
            key = self._advance()
            if key.text in seen:
                raise StructuralError(f"Duplicate '{key.text}' property found", key.loc)
            seen.add(key.text)
            self._expect("COLON", f"Expected ':' after {key.text}")
            if key.text in {"label", "doc", "context"}:
                value = self._string(f"{key.text} must be a string")
                if key.text == "context":
                    context = value
                else:
                    result[key.text] = value
            elif key.text == "cite":
                result["citation_refs"] = self._citation_references()
            else:
                metadata_value, end = self._property_block()
                result["properties"] = metadata_value
            end = self._previous()
        return result, context, end

    def _citation_references(self) -> list[CitationReference]:
        if self._at("IDENT"):
            token = self._advance()
            return [CitationReference(id=token.text, loc=token.loc)]
        self._expect("LBRACKET", "Expected citation id or '['")
        refs = [
            CitationReference(id=token.text, loc=token.loc)
            for token in self._identifiers()
        ]
        self._expect("RBRACKET", "Expected ']' after citation ids")
        return refs

    def _expression(self) -> Expression:
        identifier = self._identifier("Expected expression")
        if not self._at("LPAREN"):
            if identifier.text in _OPERATORS:
                raise SRGSyntaxError(
                    f"'{identifier.text}' is a reserved keyword", identifier.loc
                )
            return Expression(
                root=ReferenceExpression(
                    type="reference", id=identifier.text, loc=identifier.loc
                )
            )
        if identifier.text not in _OPERATORS:
            raise SRGSyntaxError(
                f"Unknown expression {identifier.text!r}", identifier.loc
            )
        self._advance()
        if identifier.text == "not":
            expression = self._expression()
            end = self._expect("RPAREN", "Expected ')' after not expression")
            return Expression(
                root=NotExpression(
                    type="not",
                    expr=expression,
                    loc=Location(start=identifier.loc.start, end=end.loc.end),
                )
            )
        if identifier.text in {"atleast", "atmost", "exactly"}:
            count = self._expect("NUMBER", "Expected integer count")
            if "." in count.text:
                raise SRGSyntaxError("Aggregator count must be an integer", count.loc)
            self._expect("COMMA", "Expected ',' after aggregator count")
            arguments = self._expressions()
            end = self._expect("RPAREN", "Expected ')' after aggregator arguments")
            location = Location(start=identifier.loc.start, end=end.loc.end)
            count_value = int(count.text)
            if identifier.text == "atleast":
                if count_value < 1:
                    raise StructuralError("atleast count must be at least 1", count.loc)
                return Expression(
                    root=AtLeastExpression(
                        type="atleast", count=count_value, args=arguments, loc=location
                    )
                )
            if count_value < 0:
                raise StructuralError(
                    f"{identifier.text} count must be non-negative", count.loc
                )
            if identifier.text == "atmost":
                return Expression(
                    root=AtMostExpression(
                        type="atmost", count=count_value, args=arguments, loc=location
                    )
                )
            return Expression(
                root=ExactlyExpression(
                    type="exactly", count=count_value, args=arguments, loc=location
                )
            )

        arguments = self._expressions()
        end = self._expect("RPAREN", "Expected ')' after aggregator arguments")
        location = Location(start=identifier.loc.start, end=end.loc.end)
        if identifier.text == "all":
            return Expression(
                root=AllExpression(type="all", args=arguments, loc=location)
            )
        if identifier.text == "any":
            return Expression(
                root=AnyExpression(type="any", args=arguments, loc=location)
            )
        return Expression(
            root=NoneExpression(type="none", args=arguments, loc=location)
        )

    def _expressions(self) -> list[Expression]:
        if self._at("RPAREN"):
            raise StructuralError(
                "Aggregators require at least one argument", self._peek().loc
            )
        expressions = [self._expression()]
        while self._at("COMMA"):
            comma = self._advance()
            if self._at("RPAREN"):
                raise SRGSyntaxError(
                    "Trailing commas are not allowed in aggregators", comma.loc
                )
            expressions.append(self._expression())
        return expressions

    def _property_block(self) -> tuple[dict[str, Any], _Token]:
        self._expect("LBRACE", "Expected '{'")
        values: dict[str, Any] = {}
        while not self._at("RBRACE"):
            key = self._identifier("Expected property name")
            self._expect("COLON", "Expected ':' after property name")
            values[key.text] = self._property_value()
            if self._at("COMMA"):
                self._advance()
                if self._at("RBRACE"):
                    break
            elif not self._at("RBRACE") and not self._at("IDENT"):
                raise SRGSyntaxError(
                    "Expected ',' or '}' after property", self._peek().loc
                )
        return values, self._expect("RBRACE", "Expected '}' after properties")

    def _property_value(self) -> Any:
        if self._at("STRING"):
            return self._string("Expected string")
        if self._at("NUMBER"):
            token = self._advance()
            return float(token.text) if "." in token.text else int(token.text)
        if self._at("IDENT") and self._peek().text in {"true", "false"}:
            return self._advance().text == "true"
        if self._at("LBRACKET"):
            self._advance()
            values: list[Any] = []
            if not self._at("RBRACKET"):
                values.append(self._property_value())
                while self._at("COMMA"):
                    self._advance()
                    if self._at("RBRACKET"):
                        break
                    values.append(self._property_value())
            self._expect("RBRACKET", "Expected ']' after array")
            return values
        if self._at("LBRACE"):
            return self._property_block()[0]
        raise SRGSyntaxError("Expected a property value", self._peek().loc)

    def _citation_regions(
        self, identifier: _Token, raw_regions: Any
    ) -> list[CitationRegion] | None:
        if raw_regions is None:
            return None
        if not isinstance(raw_regions, list):
            raise StructuralError(
                f"Citation '{identifier.text}': regions must be an array",
                identifier.loc,
            )
        regions: list[CitationRegion] = []
        for index, region in enumerate(raw_regions):
            if not isinstance(region, dict):
                raise StructuralError(
                    f"Citation '{identifier.text}': region {index} must be an object",
                    identifier.loc,
                )
            page = region.get("page")
            box = region.get("box")
            if (
                not isinstance(page, int | float)
                or isinstance(page, bool)
                or page < 0
                or (isinstance(page, float) and not page.is_integer())
            ):
                raise StructuralError(
                    f"Citation '{identifier.text}': region {index} missing required field: page",
                    identifier.loc,
                )
            if not isinstance(box, list) or len(box) != 4:
                raise StructuralError(
                    f"Citation '{identifier.text}': region {index} box must be an array of 4 vertices",
                    identifier.loc,
                )
            if not all(
                isinstance(vertex, list)
                and len(vertex) == 2
                and all(
                    isinstance(value, int | float) and not isinstance(value, bool)
                    for value in vertex
                )
                for vertex in box
            ):
                raise StructuralError(
                    f"Citation '{identifier.text}': region {index} box must contain 4 coordinate pairs [[x, y], ...]",
                    identifier.loc,
                )
            regions.append(CitationRegion(page=int(page), box=box))
        return regions

    def _identifiers(self) -> list[_Token]:
        identifiers = [self._identifier("Expected identifier")]
        while self._at("COMMA"):
            self._advance()
            if self._at("RBRACKET"):
                break
            identifiers.append(self._identifier("Expected identifier after ','"))
        return identifiers

    def _string(self, message: str) -> str:
        token = self._expect("STRING", message)
        if token.text.startswith('"""'):
            return token.text[3:-3].strip(_STRING_TRIM_CHARACTERS)
        try:
            value = json.loads(token.text)
            if not isinstance(value, str):
                raise SRGSyntaxError(f"Invalid string literal: {token.text}", token.loc)
        except json.JSONDecodeError as error:
            raise SRGSyntaxError(
                f"Invalid string literal: {token.text}", token.loc
            ) from error
        else:
            return value

    def _identifier(self, message: str) -> _Token:
        return self._expect("IDENT", message)

    def _expect(self, kind: str, message: str) -> _Token:
        if not self._at(kind):
            raise SRGSyntaxError(message, self._peek().loc)
        return self._advance()

    def _at(self, kind: str) -> bool:
        return self._peek().kind == kind

    def _peek(self) -> _Token:
        return self.tokens[self.index]

    def _peek_next(self) -> _Token:
        return self.tokens[min(self.index + 1, len(self.tokens) - 1)]

    def _advance(self) -> _Token:
        token = self._peek()
        self.index += 1
        return token

    def _previous(self) -> _Token:
        return self.tokens[self.index - 1]


def parse_srg(source: str) -> SourceFile:
    """Parse SRG source into the AST consumed by :mod:`.compiler`."""
    return _Parser(source).parse()
