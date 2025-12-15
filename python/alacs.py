from abc import ABC, abstractmethod
from collections import UserString
from collections.abc import Mapping, Sequence
from enum import StrEnum, auto
from io import BytesIO, StringIO
from typing import Any, ClassVar, TypeAlias

# multiple inheritance (from builtins in particular) means that __slots__ and __init__
# must be written as below to avoid TypeError about instance lay-out conflict.

Encoded: TypeAlias = bytes | bytearray | memoryview
String: TypeAlias = str | UserString


class UTF8(list[Encoded]):

    def __init__(self, *lines: Encoded | String):
        super().__init__(lines)  # type: ignore
        for index, line in enumerate(self):
            match line:
                case str() | UserString():
                    self[index] = line.encode()

    __slots__ = ()

    def __bytes__(self) -> bytes:
        return b'\n'.join(self)

    def __str__(self) -> str:
        return bytes(self).decode()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}={str(self)}>"


# =====================================================================================


class Comment(UTF8):
    starting_line: int  # = 0

    def __init__(self, *lines: Encoded | String):
        super().__init__(*lines)
        self.starting_line = 0

    __slots__ = ('starting_line',)


class Value(ABC):
    starting_line: int  # = 0
    comment_after: Comment | None  # = None

    __slots__ = ()


class Style(StrEnum):
    LONG_EMPTY = auto()
    SINGLE_LINE = auto()
    MARKDOWN = auto()


class Text(UTF8, Value):
    style: Style | None  # = None

    def __init__(self, *lines: Encoded | String):
        super().__init__(*lines)
        self.starting_line = 0
        self.comment_after = None
        self.style = None

    __slots__ = ('starting_line', 'comment_after', 'style')


class Array(Value, ABC):
    comment_intro: Comment | None  # = None

    @abstractmethod
    def __len__(self) -> int:
        pass

    __slots__ = ()


class List(list[Value], Array):

    def __init__(self, *values: Value):
        super().__init__(values)
        self.starting_line = 0
        self.comment_after = None
        self.comment_intro = None

    __slots__ = ('starting_line', 'comment_after', 'comment_intro')


class Key(str):
    blank_line_before: bool  # = False
    comment_before: Comment | None  # = None

    def __init__(self, handled_by_str_new_but_here_for_type_hint: Any):
        self.blank_line_before = False
        self.comment_before = None

    __slots__ = ('blank_line_before', 'comment_before')


class Dict(dict[Key, Value], Array):

    def __init__(self, **values: Value):
        super().__init__((Key(k), v) for k, v in values.items())
        self.starting_line = 0
        self.comment_after = None
        self.comment_intro = None

    __slots__ = ('starting_line', 'comment_after', 'comment_intro')


class File(Dict):
    hashbang: Comment | None = None


# ========================================================================= ThreadLocal


class Indent:

    def __init__(self, value: bytes):
        if value.count(b'\t') != len(value):
            raise AssertionError("indent must be tab chars only")
        self._bytes = value
        self._more: Indent | None = None
        self._less: Indent | None = None
        self._key: Any = None

    __slots__ = ("_bytes", "_more", "_less", "_key")

    def more(self) -> 'Indent':
        result = self._more
        if result is None:
            result = self._more = Indent(self._bytes + b'\t')
            result._less = self
        return result

    def less(self) -> 'Indent':
        result = self._less
        if result is None:
            raise AssertionError("indent can't go negative")
        return result

    def keys(self) -> str:
        if self._less is None:
            return '' if self._key is None else f"{self._key}"
        match self._key:
            case None: return ''
            case str(key): return f"{self.less().keys()}.{key}"
            case key: return f"{self.less().keys()}[{key}]"

    def zero(self) -> 'Indent':
        result = self
        while result:
            result = result.less()
        indent = result
        while indent is not None:
            indent._key = None
            indent = indent._more
        return result

    def __len__(self) -> int:
        return len(self._bytes)

    def __repr__(self) -> str:
        return f"<Indent#{len(self)}@{self.keys()}>"


class Memory:
    empty: ClassVar[memoryview] = memoryview(b'')

    def __init__(self):
        super().__init__()
        self._scratch = list[Encoded]()
        self._errors = list[str]()
        self._indent: Indent = Indent(b'')
        self._count: int = 0
        self._write = BytesIO()
        self._parse = Memory.empty
        self._next: int = -1
        self._line = Memory.empty
        self._tabs: int = -1

    __slots__ = ("_scratch", "_errors", "_indent", "_count",
                 "_write", "_parse", "_next", "_line", "_tabs")

    # ============================================================================ UTF8

    def normalize(self, utf8: UTF8) -> None:
        if 1 == len(utf8) and 0 == len(utf8[0]):
            utf8.clear()  # `[]` is more "True"ly empty than `[b'']`
        else:
            self._scratch.clear()
            for index in range(len(utf8) - 1, -1, -1):
                chunk = utf8[index]
                if not isinstance(chunk, memoryview):
                    if b'\n' not in chunk:
                        continue
                    chunk = memoryview(chunk)
                start = len(chunk) - 1
                while 0 <= start and 10 != chunk[start]:
                    start -= 1
                if 0 <= start:
                    self._scratch.append(chunk[start+1:])
                    limit = start
                    start -= 1
                    while start >= 0:
                        if 10 == chunk[start]:
                            self._scratch.append(chunk[start+1:limit])
                            limit = start
                        start -= 1
                    self._scratch.append(chunk[:limit])
                    self._scratch.reverse()
                    utf8[index:index+1] = self._scratch
                    self._scratch.clear()

    # ========================================================================== errors

    def _error(self, message: str) -> str:
        match self._errors:
            case []:
                return message
            case _:
                return f"{message}:\n\t{'\n\t'.join(self._errors)}"

    def _errors_add(self, *parts: Any) -> None:
        line = StringIO()
        if self._count:
            line.write(f"#{self._count} ")
        line.write(self._indent.keys())
        if parts:
            line.write(":")
            for part in parts:
                line.write(" ")
                line.write(str(part))
        self._errors.append(line.getvalue())

    # ======================================================================= to python

    def python(self, any: Value) -> str | list | dict:
        """Convert a `Value` to simple Python data.

        Returns a deep copy with any `Text` replaced by `str` instances,
        and the arrays replaced by their builtin analogs.
        """
        self._errors.clear()
        self._indent = self._indent.zero()
        try:
            match self._python(any):
                case _ if self._errors:
                    raise ValueError(self._error(
                        "argument is or contains illegal non-`Value` data"))
                case None:
                    raise AssertionError("impossible: got None, but no error")
                case result:
                    return result
        finally:
            self._errors.clear()
            self._indent = self._indent.zero()

    def _python(self, any: Value) -> str | list | dict | None:
        match any:
            case Text():
                return str(any)
            case List():
                result = list()
                self._indent = self._indent.more()
                for key, value in enumerate(any):
                    self._indent._key = key
                    result.append(self._python(value))
                self._indent = self._indent.less()
                return result
            case Dict():
                result = dict()
                self._indent = self._indent.more()
                for key, value in any.items():
                    self._indent._key = key
                    match key:
                        case Key():
                            result[str(key)] = self._python(value)
                        case other:
                            self._errors_add("key is", type(other))
                self._indent = self._indent.less()
                return result
        self._errors_add("value is", type(any))

    # ===================================================================== from python

    def file(self, mapping: Mapping) -> File:
        """Convert a simple Python `dict` (any mapping) to a `File`.

        Returns deep copy except bytes/bytearray/memoryview are shared
        (even though some of those are mutable)."""
        self._errors.clear()
        self._indent = self._indent.zero()
        try:
            match self._value(mapping):
                case _ if self._errors:
                    raise ValueError(self._error(
                        "argument contains data that can't be converted to `Value`"))
                case None:
                    raise AssertionError("impossible: got None, but no error")
                case File() as result:
                    return result
                case other:
                    raise AssertionError(f"impossible: got {type(other)}")
        finally:
            self._scratch.clear()
            self._errors.clear()
            self._indent = self._indent.zero()

    def _value(self, any: Any) -> Value | None:
        match any:
            case None:
                return Text()
            case str() | UserString() | bytes() | bytearray() | memoryview():
                result = Text(any)
                self.normalize(result)
                return result
            case Sequence():
                result = List()
                self._indent = self._indent.more()
                for i, v in enumerate(any):
                    self._indent._key = i
                    x = self._value(v)
                    if x is not None:
                        result.append(x)
                self._indent = self._indent.less()
                return result
            case Mapping():
                result = Dict() if self._indent else File()
                self._indent = self._indent.more()
                for k, v in any.items():
                    self._indent._key = k
                    if isinstance(k, (str, UserString)):
                        x = self._value(v)
                        if x is not None:
                            result[Key(k)] = x
                    else:
                        self._errors_add("key is", type(k))
                self._indent = self._indent.less()
                return result
        self._errors_add("value is", type(any))

    # ========================================================================== encode

    def encode(self, file: File) -> memoryview:
        """result must be `release`d - suggest use `with`."""
        self._errors.clear()
        self._indent = self._indent.zero()
        try:
            self._count = 1
            self._write.seek(0)
            self._write.truncate()
            self._writeComment(file.hashbang)
            self._writeDict(file)
            self._writeComment(file.comment_after)
            if self._errors:
                raise ValueError(self._error(
                    "argument is or contains illegal non-`Value` data"))
            return self._write.getbuffer()
        finally:
            self._scratch.clear()
            self._errors.clear()
            self._indent = self._indent.zero()

    def _writeln(self, key: Key | None, marker: bytes, data: Encoded) -> None:
        out = self._write
        if 1 != self._count:
            out.write(b'\n')
        out.write(self._indent._bytes)
        if key:
            out.write(key.encode())  # trusted because ctor
        if marker:
            out.write(marker)  # trusted because literal
        if data:
            if 10 in data:
                raise AssertionError("impossible: normalized has LF")
            out.write(data)
        self._count += 1

    def _writeComment(self, comment: Comment | None) -> None:
        if comment is not None:
            comment.starting_line = self._count
            self.normalize(comment)
            match len(comment):
                case 0:
                    self._writeln(None, b'#', b'')
                case 1:
                    self._writeln(None, b'#', comment[0])
                case _:
                    lines = iter(comment)
                    self._writeln(None, b'#', next(lines))
                    for line in lines:
                        self._writeln(None, b'\t', line)

    def _writeText(self, text: Text) -> None:
        if text:
            if text.style == Style.LONG_EMPTY:
                self._errors_add("Text is not LONG_EMPTY")
            for line in text:
                self._writeln(None, b'', line)
        elif text.style == Style.LONG_EMPTY:
            self._writeln(None, b'', b'')

    def _writeList(self, array: List) -> None:
        self._writeComment(array.comment_intro)
        for index, value in enumerate(array):
            self._indent._key = index
            self._writeValue(None, value)

    def _writeDict(self, array: Dict) -> None:
        self._writeComment(array.comment_intro)
        for key, value in array.items():
            self._indent._key = key
            match key:
                case Key():
                    if key.blank_line_before:
                        self._writeln(None, b'', b'')
                    self._writeComment(key.comment_before)
                    self._writeValue(key, value)
                case other:
                    self._errors_add("key is", type(other))

    def _writeValue(self, key: Key | None, value: Value) -> None:
        value.starting_line = self._count
        match value:
            case Text():
                self.normalize(value)
                style = value.style
                if style == Style.SINGLE_LINE and len(value) > 1:
                    self._errors_add("Text is not SINGLE_LINE")
                    style = None
                if style == Style.SINGLE_LINE:
                    marker = b'' if key is None else b'='
                    text = b'' if not value else value[0]
                    self._writeln(key, marker, text)
                else:
                    marker = b'>' if value.style == Style.MARKDOWN else b'|'
                    self._writeln(key, marker, b'')
                    self._indent = self._indent.more()
                    self._writeText(value)
                    self._indent = self._indent.less()
            case List():
                self._writeln(key, b'[]', b'')
                self._indent = self._indent.more()
                self._writeList(value)
                self._indent = self._indent.less()
            case Dict():
                self._writeln(key, b':', b'')
                self._indent = self._indent.more()
                self._writeDict(value)
                self._indent = self._indent.less()
            case other:
                self._errors_add("value is", type(other))
        self._writeComment(value.comment_after)

    # ========================================================================== decode

    def decode(self, alacs: bytes) -> File:
        self._errors.clear()
        self._indent = self._indent.zero()
        try:
            self._count = 0
            self._parse = memoryview(alacs)
            self._next = 0
            file = File()
            self._readln()
            if len(self._line) > 1 and self._line[0] == 35 and self._line[1] == 33:
                file.hashbang = self._readComment()
            self._readDictEntries(file)
            if len(self._line) > 1 and self._line[0] == 35:
                file.comment_after = self._readComment()
            if self._errors:
                raise ValueError(self._error("parse errors"))
            return file
        finally:
            self._scratch.clear()
            self._errors.clear()
            self._indent = self._indent.zero()
            self._parse = self._line = Memory.empty

    def _readln(self) -> bool:
        if self._next < 0:
            self._line = Memory.empty
            self._tabs = -1
            return False
        # no memoryview.index (yet), so assume that _parse wraps a bytes...
        index = self._parse.obj.find(10, self._next)  # type: ignore
        if index < 0:
            self._line = self._parse[self._next:]
            self._next = -1
        else:
            self._line = self._parse[self._next:index]
            index += 1
            self._next = index if index < len(self._parse) else -1
        index = 0
        while index < len(self._line) and self._line[index] == 9:
            index += 1
        self._tabs = index
        self._count += 1
        return True

    class _Marker(StrEnum):
        PLAINTEXT = "|"
        MARKDOWN = ">"
        LIST = "[]"
        DICT = ":"
        COMMENT = "#"

    def _marker(self) -> _Marker | None:
        over = len(self._line) - len(self._indent)
        if over <= 0:
            return None
        match self._line[-1]:
            case 124: return Memory._Marker.PLAINTEXT
            case 62: return Memory._Marker.MARKDOWN
            case 93 if over > 1 and self._line[-2] == 91:
                return Memory._Marker.LIST
            case 58: return Memory._Marker.DICT
        if self._line[len(self._indent)] == 35:
            return Memory._Marker.COMMENT
        return None

    def _readKey(self, drop: int) -> Key | None:
        if len(self._line) < len(self._indent) + drop:
            return None
        else:
            return Key(self._line[len(self._indent):-drop].tobytes().decode())

    def _readComment(self) -> Comment:
        assert self._marker() == Memory._Marker.COMMENT, f"comment != {self._marker()}"
        comment = Comment()
        comment.starting_line = self._count
        comment.append(self._line[len(self._indent)+1:])
        while self._readln() and self._tabs > len(self._indent):
            comment.append(self._line[len(self._indent)+1:])
        return comment

    def _readText(self, markdown: bool) -> Text:
        marker = Memory._Marker.MARKDOWN if markdown else Memory._Marker.PLAINTEXT
        assert self._marker() == marker, f"text != {self._marker()}"
        text = Text()
        text.starting_line = self._count
        if markdown:
            text.style = Style.MARKDOWN
        while self._readln() and self._tabs > len(self._indent):
            text.append(self._line[len(self._indent)+1:])
        if len(text) == 1 and len(text[0]) == 0:
            text.clear()
            text.style = Style.LONG_EMPTY
        if self._marker() == Memory._Marker.COMMENT:
            text.comment_after = self._readComment()
        return text

    def _readList(self) -> List:
        assert self._marker() == Memory._Marker.LIST, f"list != {self._marker()}"
        array = List()
        array.starting_line = self._count
        if not self._readln():
            return array
        self._indent = self._indent.more()
        if self._marker() == Memory._Marker.COMMENT:
            array.comment_intro = self._readComment()
        self._readListItems(array)
        self._indent = self._indent.less()
        if self._marker() == Memory._Marker.COMMENT:
            array.comment_after = self._readComment()
        return array

    def _readListItems(self, array: List) -> None:
        while self._tabs >= len(self._indent):
            match self._marker():
                case Memory._Marker.PLAINTEXT:
                    array.append(self._readText(False))
                case Memory._Marker.MARKDOWN:
                    array.append(self._readText(True))
                case Memory._Marker.LIST:
                    array.append(self._readList())
                case Memory._Marker.DICT:
                    array.append(self._readDict())
                case Memory._Marker.COMMENT:
                    self._errors_add("misplaced comment")
                case None:
                    text = Text(self._line[len(self._indent):])
                    text.style = Style.SINGLE_LINE
                    array.append(text)

    def _readDict(self) -> Dict:
        assert self._marker() == Memory._Marker.DICT, f"dict != {self._marker()}"
        array = Dict()
        array.starting_line = self._count
        if not self._readln():
            return array
        self._indent = self._indent.more()
        if self._marker() == Memory._Marker.COMMENT:
            array.comment_intro = self._readComment()
        self._readDictEntries(array)
        self._indent = self._indent.less()
        if self._marker() == Memory._Marker.COMMENT:
            array.comment_after = self._readComment()
        return array

    def _readDictEntries(self, array: Dict) -> None:
        duplicates = set[Key]()
        blank = False
        comment:Comment|None = None
        first = len(self._indent)
        while self._tabs >= first:
            match self._marker():
                case Memory._Marker.PLAINTEXT:
                    key = Key(self._line[first:-1].tobytes().decode())
                    value = self._readText(False)
                case Memory._Marker.MARKDOWN:
                    key = Key(self._line[first:-1].tobytes().decode())
                    value = self._readText(True)
                case Memory._Marker.LIST:
                    key = Key(self._line[first:-2].tobytes().decode())
                    value = self._readList()
                case Memory._Marker.DICT:
                    key = Key(self._line[first:-1].tobytes().decode())
                    value = self._readDict()
                case Memory._Marker.COMMENT:
                    if comment:
                        self._errors_add("misplaced comment")
                    comment = self._readComment()
                    continue
                case None if len(self._line) == first:
                    if blank:
                        self._errors_add("multiple blank lines")
                    if comment:
                        self._errors_add("blank line must precede comment")
                    blank = True
                    self._readln()
                    continue
                case None: # and guard for previous case failed
                    index = first
                    assert len(self._line) > index, "blank in wrong case"
                    # no memoryview.index (yet)...
                    while self._line[index] != 61:
                        index += 1
                        if index >= len(self._line):
                            self._errors_add("expected `=`")
                            index = -1
                            break
                    self._readln()
                    if index < 0:
                        continue
                    key = Key(self._line[first:index].tobytes().decode())
                    value = Text(self._line[index+1:])
                case _:
                    raise RuntimeError("match cases are not exhaustive?")
            if key in array:
                duplicates.add(key)
            if blank:
                key.blank_line_before = True
                blank = False
            if comment:
                key.comment_before = comment
                comment = None
            array[key] = value
        if duplicates:
            self._errors_add(f"duplicate keys: {duplicates}")
