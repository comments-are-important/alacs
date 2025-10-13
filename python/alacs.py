import re, threading
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence, Callable, Iterator
from io import StringIO
from pathlib import Path
from typing import Any, Optional, Self, Iterable, ClassVar, TypeVar, TextIO


anyTextIO = TypeVar('anyTextIO', bound=TextIO)
anyBreakChar = re.compile(r'[\f\n\r\v\u2028\u2029]')


class Indent(str):
    _more:Optional['Indent']=None
    _less:Optional['Indent']=None

    def __init__(self, handled_by_str_new_but_here_for_linting: Any):
        if self.count('\t') != len(self):
            raise ValueError("indent must be tab chars")

    def more(self) -> 'Indent':
        result = self._more
        if result is None:
            result = self._more = Indent(self + '\t')
            result._less = self
        return result

    def less(self) -> 'Indent':
        result = self._less
        if result is None:
            raise ValueError("no negative indent")
        return result

    def apply(self, key: str, mark: str, line: str) -> str:
        if '\n' in line:
            raise ValueError("line must not contain newline char")
        return f"{self}{key}{mark}{line}\n"

    def each(self, source: Iterable[str] | None, output: TextIO, mark: str) -> None:
        if source:
            for line in source:
                output.write(self.apply('', mark, line))


class Key(str):
    comments_before: Iterable[str] | None = None

    def __init__(self, handled_by_str_new_but_here_for_linting: Any):
        if not self.isidentifier():
            raise ValueError(f"Keys must be identifiers: {self}")

    def before(self, indent: Indent, output: TextIO) -> None:
        if self.comments_before:
            output.write('\n')
            indent.each(self.comments_before, output, '#')

    @staticmethod
    def parse(indent: Indent, parser: 'Parser') -> Iterable[str] | None:
        if parser.input.closed:
            return None
        if parser.end:
            if not parser.begins(indent):
                raise RuntimeError(f"{parser.number} expected Key")
            return None
        parser.step()
        comments = parser.comments(indent)
        if not parser.begins(indent):
            raise RuntimeError(f"{parser.number} expected Key")
        return comments


class Element(ABC):
    marker: ClassVar[str]
    comments_after: Iterable[str] | None = None

    @staticmethod
    def of(any: Any) -> 'Element':
        match any:
            case None:
                return String('')
            case str():
                return Text(any) if anyBreakChar.search(any) else String(any)
            case Sequence():
                return List(Element.of(v) for v in any)
            case Mapping():
                return Dict((Key(k), Element.of(v)) for k, v in any.items())
        raise ValueError(f"no Element for {type(any)}")

    def abbrev(self) -> str | None:
        return None

    def finish(self, indent: Indent, output: TextIO) -> None:
        """indent must be one more than it was for the marker line"""
        pass

    # @staticmethod
    # def parse(value: str, indent: Indent, parser: 'Parser') -> 'Element':
    #     match value:
    #         case '>': elt = Text.parse(indent.more(), parser)
    #         case '[]': elt = List().parse(indent.more(), parser)
    #         case ':': elt = Dict().parse(indent.more(), parser)
    #         case _: elt = String(value)
    #     parser.step()
    #     elt.comments_after = parser.comments(indent)
    #     return elt


class String(str, Element):
    marker = '='

    def __init__(self, handled_by_str_new_but_here_for_linting: Any):
        if anyBreakChar.search(self):
            raise ValueError("must use Text because of break char")

    def abbrev(self) -> str:
        match self:
            case ">": return "'>'"
            case "[]": return "'[]'"
            case ":": return "':'"
        return self

    @staticmethod
    def parse(value: str) -> 'String':
        match value:
            case "'>'": return String('>')
            case "'[]'": return String('[]')
            case "':'": return String(':')
        return String(value)


class Text(str, Element):
    marker = '>'

    def finish(self, indent: Indent, output: TextIO) -> None:
        indent.each(self.split('\n'), output, '')

    @staticmethod
    def parse(indent: Indent, parser: 'Parser') -> 'Text':
        if not parser.begins(indent):
            raise RuntimeError(f"{parser.number}: Text must have content")
        buffer = StringIO(parser.extract(len(indent)))
        parser.step()
        while parser.begins(indent):
            buffer.write('\n')
            buffer.write(parser.extract(len(indent)))
            parser.step()
        return Text(buffer.getvalue())


class List(list[Element], Element):
    marker = '[]'
    comments_intro: Iterable[str] | None = None

    def finish(self, indent: Indent, output: TextIO) -> None:
        indent.each(self.comments_intro, output, '#')
        for value in self:
            abbrev = value.abbrev()
            marker = value.marker if abbrev is None else ''
            output.write(indent.apply('', marker, abbrev or ''))
            value.finish(indent.more(), output)
            indent.each(value.comments_after, output, '#')

    def parse(self, indent: Indent, parser: 'Parser') -> 'List':
        self.comments_intro = parser.comments(indent)
        while parser.begins(indent):
            if parser.line.count(Text.marker,)
            match parser.extract(len(indent)):

                case '>': elt = Text.parse(indent.more(), parser)
                case '[]': elt = List().parse(indent.more(), parser)
                case ':': elt = Dict().parse(indent.more(), parser)
                case _ as value: elt = String(value)
            parser.step()
            elt.comments_after = parser.comments(indent)
            self.append(Element.parse(value, indent, parser))
            parser.step()
        return self


class Dict(dict[Key, Element], Element):
    marker = ':'
    comments_intro: Iterable[str] | None = None

    def finish(self, indent: Indent, output: TextIO) -> None:
        indent.each(self.comments_intro, output, '#')
        for key, value in self.items():
            key.before(indent, output)
            abbrev = value.abbrev()
            marker = value.marker
            output.write(indent.apply(key, marker, abbrev or ''))
            value.finish(indent.more(), output)

    def parse(self, indent: Indent, parser: 'Parser') -> Self:
        self.comments_intro = parser.comments(indent)
        while parser.end == 0 or parser.begins(indent):
            key_comments = Key.parse(indent, parser)
            value = lines.line[len(indent):]
            key, value = value.split('=', 1)
            key = Key(key)
            key.comments_before = key_comments
            elt = Element.parse(value, indent, lines)
            elt.comments_after = indent.parse(lines)
            self[key] = elt
            if lines.line == '':
                lines.step()
                key_comments = indent.parse(lines)
            else:
                key_comments = ()
        return self


class Parser:
    input: TextIO
    line: str
    end: int
    number: int

    def __init__(self, source: str | Path):
        self.input = (StringIO(source) if isinstance(source, str)
                      else source.open(encoding="utf-8", newline='\n'))
        self.line = ''
        self.end = 0
        self.number = 0
        self.step()

    def step(self) -> None:
        if not self.input.closed:
            self.line = self.input.readline()
            self.number += 1
            if not self.line:
                self.input.close()
                self.end = 0
            else:
                self.end = len(self.line)
                self.end -= self.line.count('\n', self.end - 1)

    def extract(self, start: int) -> str:
        return self.line[start:self.end]

    def begins(self, indent: Indent, mark: str = '') -> bool:
        if not self.line.startswith(indent):
            return False
        start = len(indent) + len(mark)
        if mark and not self.line.count(mark, len(indent), start):
            return False
        return True

    def comments(self, indent: Indent) -> Iterable[str] | None:
        if not self.begins(indent, '#'):
            return None
        result = [self.extract(len(indent)+1)]
        while self.begins(indent, '#'):
            result.append(self.extract(len(indent)+1))


class ALACS:
    _zero_indent = Indent('')

    def write(self, alacs: Dict, out: anyTextIO) -> anyTextIO:
        assert not alacs.comments_after
        alacs.finish(self._zero_indent, out)
        return out

    def encode(self, alacs: Dict) -> str:
        return self.write(alacs, StringIO(newline='\n')).getvalue()

    def load(self, path: Path):
        with path.open(encoding='utf8', newline='\n') as stream:
            for line in stream:
                ...


def main():
    return Element.of({
        "k1": "v1",
        "k2": "v2\nv2\nv2",
        "k3": [
            "v3.1",
            "v3.2\nv3.2",
            {
                "k3_3_1": "v3.3.1",
            }
        ],
        "k4": {}
    })
