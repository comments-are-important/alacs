import re
from abc import abstractmethod
from collections.abc import Mapping, Sequence, Callable, Iterator
from io import StringIO
from pathlib import Path
from typing import Any, Optional, Self, ClassVar, TypeVar, TextIO


anyTextIO = TypeVar('anyTextIO', bound=TextIO)
anyBreakChar = re.compile(r'[\f\n\r\v\u2028\u2029]')


class Indent(str):
    _instances: ClassVar[list['Indent']] = []

    @staticmethod
    def of(value: int | str) -> 'Indent':
        if isinstance(value, str):
            line = value
            value = 0
            while line.count('\t', value, value+1):
                value += 1
        if value < 0:
            raise ValueError("Indent can't be negative")
        if not Indent._instances:
            Indent('')  # added in __init__
        while len(Indent._instances) <= value:
            Indent(Indent._instances[-1] + '\t')  # added in __init__
        return Indent._instances[value]

    def __init__(self, handled_by_str_new_but_here_for_linting: Any):
        if not (len(self) == len(Indent._instances) == self.count('\t')):
            raise RuntimeError("use 'of', 'more', or 'less' (not constructor)")
        Indent._instances.append(self)
        self.hash = f"{self}#"

    def more(self) -> 'Indent':
        return Indent.of(len(self) + 1)

    def less(self) -> 'Indent':
        return Indent.of(len(self) - 1)

    def comments(self, source: Sequence[str], add_line: Callable[[str], None]) -> None:
        for comment in source:
            add_line(f"{self.hash}{comment}")

    def parse(self, lines: 'LineStepper') -> Sequence[str]:
        if lines.line is None or not lines.line.startswith(self.hash):
            return ()
        comments = list[str]()
        while lines.line is not None and lines.line.startswith(self.hash):
            comments.append(lines.line[len(self.hash):])
            lines.step()
        return comments


class LineStepper:
    iterator: Iterator[str] | None
    line: str | None
    number: int

    def __init__(self, source: str):
        self.iterator = iter(StringIO(source))
        self.line = ''
        self.number = 0
        self.step()

    def step(self) -> Self:
        if self.iterator is not None:
            line = self.line = next(self.iterator, None)
            self.number += 1
            if line is None:
                self.iterator = None
            elif line and line.endswith('\n'):
                self.line = line[0:-1]
        return self


class Key(str):
    comments_before: Sequence[str] = ()

    def __init__(self, handled_by_str_new_but_here_for_linting: Any):
        if not self.isidentifier():
            raise ValueError(f"Keys must be identifiers: {self}")


class Element:
    comments_after: Sequence[str] = ()

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

    @abstractmethod
    def start_no_key(self, indent: Indent) -> str:
        pass

    @abstractmethod
    def start(self, indent: Indent, key: Key) -> str:
        pass

    def finish(self, indent: Indent, add_line: Callable[[str], None]) -> None:
        """indent should be one more than what was given to start"""
        if self.comments_after:
            indent.less().comments(self.comments_after, add_line)

    @staticmethod
    def parse(value: str, indent: Indent, lines: LineStepper) -> 'Element':
        if value.startswith('\t'):
            raise ValueError(f"{lines.number}: excess indentation")
        match value:
            case '>': return Text.parse(indent.more(), lines.step())
            case '[]': return List().parse(indent.more(), lines.step())
            case ':': return Dict().parse(indent.more(), lines.step())
        lines.step()
        return String.parse(value)


class String(str, Element):

    def __init__(self, handled_by_str_new_but_here_for_linting: Any):
        if anyBreakChar.search(self):
            raise ValueError("muse use Text because of break char")

    def start_no_key(self, indent: Indent) -> str:
        return f"{indent}{self.quoted()}"

    def start(self, indent: Indent, key: Key) -> str:
        return f"{indent}{key}={self.quoted()}"

    def quoted(self) -> str:
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

    def start_no_key(self, indent: Indent) -> str:
        return f"{indent}>"

    def start(self, indent: Indent, key: Key) -> str:
        return f"{indent}{key}=>"

    def finish(self, indent: Indent, add_line: Callable[[str], None]) -> None:
        for it in self.split('\n'):
            add_line(f"{indent}{it}")
        super().finish(indent, add_line)  # self.comments_after

    @staticmethod
    def parse(indent: Indent, lines: LineStepper) -> 'Text':
        buffer = StringIO()
        while lines.line is not None and lines.line.startswith(indent):
            if buffer.tell():
                buffer.write('\n')
            buffer.write(lines.line[len(indent):])
            lines.step()
        return Text(buffer.getvalue())


class List(list[Element], Element):
    comments_intro: Sequence[str] = ()

    def start_no_key(self, indent: Indent) -> str:
        return f"{indent}[]"

    def start(self, indent: Indent, key: Key) -> str:
        return f"{indent}{key}[]"

    def finish(self, indent: Indent, add_line: Callable[[str], None]) -> None:
        indent.comments(self.comments_intro, add_line)
        for value in self:
            add_line(value.start_no_key(indent))
            value.finish(indent.more(), add_line)
        super().finish(indent, add_line)  # self.comments_after

    def parse(self, indent: Indent, lines: LineStepper) -> 'List':
        self.comments_intro = indent.parse(lines)
        while lines.line is not None and lines.line.startswith(indent):
            value = lines.line[len(indent):]
            elt = Element.parse(value, indent, lines)
            elt.comments_after = indent.parse(lines)
            self.append(elt)
        return self


class Dict(dict[Key, Element], Element):
    comments_intro: Sequence[str] = ()

    def start_no_key(self, indent: Indent) -> str:
        return f"{indent}:"

    def start(self, indent: Indent, key: Key) -> str:
        return f"{indent}{key}:"

    def finish(self, indent: Indent, add_line: Callable[[str], None]) -> None:
        indent.comments(self.comments_intro, add_line)
        above = self.comments_intro
        for key, value in self.items():
            below = key.comments_before
            if above or below:
                add_line("")
            indent.comments(key.comments_before, add_line)
            add_line(value.start(indent, key))
            value.finish(indent.more(), add_line)
            above = value.comments_after
        super().finish(indent, add_line)  # self.comments_after

    def parse(self, indent: Indent, lines: LineStepper) -> Self:
        self.comments_intro = indent.parse(lines)
        if lines.line == '':
            lines.step()
            key_comments = indent.parse(lines)
        else:
            key_comments = ()
        while lines.line is not None and lines.line.startswith(indent):
            value = lines.line[len(indent):]
            key, value = value.split('=',1)
            key = Key(key)
            key.comments_before = key_comments
            elt = Element.parse(value, indent, lines)
            elt.comments_after = indent.parse(lines)
            self[key] =elt
            if lines.line == '':
                lines.step()
                key_comments = indent.parse(lines)
            else:
                key_comments = ()
        return self


class ALACS:

    @staticmethod
    def write(alacs: Dict, out: anyTextIO) -> anyTextIO:
        def write_one_line(line: str) -> None:
            assert '\n' not in line
            out.write(line)
            out.write('\n')
        alacs.finish(Indent.of(0), write_one_line)
        return out

    @staticmethod
    def encode(alacs: Dict) -> str:
        return ALACS.write(alacs, StringIO(newline='\n')).getvalue()

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
