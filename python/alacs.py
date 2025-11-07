from abc import ABC
from collections import UserString
from collections.abc import Mapping, Sequence
from io import BytesIO, StringIO
from typing import Any, TypeAlias

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


class Text(UTF8, Value):
    long_empty: bool  # = False

    def __init__(self, *lines: Encoded | String):
        super().__init__(*lines)
        self.starting_line = 0
        self.comment_after = None
        self.long_empty = False

    __slots__ = ('starting_line', 'comment_after', 'long_empty')


class Array(Value, ABC):
    comment_intro: Comment | None  # = None

    __slots__ = ()


class List(list[Value], Array):

    def __init__(self, *values: Value):
        super().__init__(values)
        self.starting_line = 0
        self.comment_after = None
        self.comment_intro = None

    __slots__ = ('starting_line', 'comment_after', 'comment_intro')


class Key(str):
    comment_before: Comment | None  # = None

    def __init__(self, handled_by_str_new_but_here_for_type_hint: Any):
        self.comment_before = None

    __slots__ = ('comment_before',)


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

    def __init__(self):
        super().__init__()
        self._errors = list[str]()
        self._indent: Indent = Indent(b'')
        self._count: int = 0
        self._utf8 = list[Encoded]()
        self._write = BytesIO()
        self._parse = memoryview(b'')
        self._next: int = 0
        self._line = self._parse
        self._tabs: int = 0

    __slots__ = ("_errors", "_indent", "_count", "_utf8",
                 "_write", "_parse", "_next", "_line", "_tabs")

    def _zero(self, count: int = 0) -> None:
        self._errors.clear()
        self._indent = self._indent.zero()
        self._count = count

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

    def python(self, value: Value) -> str | list | dict:
        """Convert a `Value` to simple Python data.

        Returns a deep copy with any `Text` replaced by `str` instances,
        and the arrays replaced by their builtin analogs.
        """
        self._zero()
        match self._python(value):
            case _ if self._errors:
                raise ValueError(self._error(
                    "argument is or contains illegal non-`Value` data"))
            case None:
                raise AssertionError("impossible: got None, but no error")
            case result:
                return result

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
                            result[key] = self._python(value)
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
        self._zero()
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

    # ============================================================================ UTF8

    def normalize(self, utf8: UTF8) -> None:
        if 1 == len(utf8) and 0 == len(utf8[0]):
            utf8.clear()  # `[]` is more "True"ly empty than `[b'']`
        else:
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
                    scratch = self._utf8
                    scratch.clear()
                    scratch.append(chunk[start+1:])
                    limit = start
                    start -= 1
                    while start >= 0:
                        if 10 == chunk[start]:
                            scratch.append(chunk[start+1:limit])
                            limit = start
                        start -= 1
                    scratch.append(chunk[:limit])
                    scratch.reverse()
                    utf8[index:index+1] = scratch
                    scratch.clear()

    # ========================================================================== encode

    def encode(self, file: File) -> memoryview:
        """result must be `release`d - suggest use `with`."""
        self._zero(1)
        self._write.seek(0)
        self._write.truncate()
        self._writeComment(file.hashbang)
        self._writeDict(file)
        self._writeComment(file.comment_after)
        if self._errors:
            raise ValueError(self._error(
                "argument is or contains illegal non-`Value` data"))
        return self._write.getbuffer()

    def _writeln(self, key: Key | None, marker: bytes, data: Encoded) -> None:
        out = self._write
        out.write(self._indent._bytes)
        if key:
            out.write(key.encode())  # trusted because ctor
        if marker:
            out.write(marker)  # trusted because literal
        if data:
            if 10 in data:
                raise AssertionError("impossible: normalized has LF")
            out.write(data)
        out.write(b'\n')
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
        self.normalize(text)
        if text.long_empty and not text:
            self._writeln(None, b'', b'')
        elif text:
            for line in text:
                self._writeln(None, b'', line)

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
                    self._writeComment(key.comment_before)
                    self._writeValue(key, value)
                case other:
                    self._errors_add("key is", type(other))

    def _writeValue(self, key: Key | None, value: Value) -> None:
        value.starting_line = self._count
        match value:
            case Text():
                self._writeln(key, b'>', b'')
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
        file = File()
        self._zero()
        self._parse = memoryview(alacs)
        self._next = 0
        self._readln()
        file.hashbang = self._readComment()
        self._readDict(file)
        file.comment_after = self._readComment()
        if self._errors:
            raise ValueError(self._error(
                "parse errors"))
        return file

    def _readln(self, limit: bool = True) -> bool:
        excess = 0
        while True:
            if self._next < 0:
                if self._line:
                    self._line = self._parse[len(self._parse):]
                    self._tabs = 0
                if excess:
                    self._errors_add(f"excessive indent from line {excess}")
                return False
            # no memoryview.index (yet), so assume that _parse wraps a bytes...
            index = self._parse.obj.find(10, self._next)  # type: ignore
            if index <= 0:
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
            if not limit or index <= len(self._indent):
                if excess:
                    self._errors_add(f"excessive indent from line {excess}")
                return True
            if not excess:
                excess = self._count

    def _readKey(self, drop: int) -> Key | None:
        if len(self._line) == self._tabs + drop:
            return None
        else:
            return Key(self._line[self._tabs:-drop].tobytes().decode())

    def _readComment(self) -> Comment | None:
        if self._tabs != len(self._indent) or len(self._line) <= self._tabs or 35 != self._line[self._tabs]:
            return None
        comment = Comment()
        comment.starting_line = self._count
        comment.append(self._line[self._tabs+1:])
        while self._readln(False) and self._tabs > len(self._indent):
            comment.append(self._line[self._tabs+1:])
        return comment

    def _readText(self, text: Text) -> None:
        while self._tabs >= len(self._indent):
            text.append(self._line[self._tabs:])
            if not self._readln(False):
                break
        if len(text) == 1 and len(text[0]) == 0:
            text.clear()
            text.long_empty = True

    def _readList(self, array: List) -> None:
        if self._next >= 0 and self._tabs == len(self._indent):
            array.comment_intro = self._readComment()
            while self._next >= 0 and self._tabs == len(self._indent):
                key, value = self._readValue(len(array))
                if key is not None:
                    self._errors_add(f"key not allowed in List: {key}")
                else:
                    array.append(value)

    def _readDict(self, array: Dict) -> None:
        if self._next >= 0 and self._tabs == len(self._indent):
            array.comment_intro = self._readComment()
            while self._next >= 0 and self._tabs == len(self._indent):
                before = self._readComment()
                key, value = self._readValue(-1)
                if key is None:
                    self._errors_add("key required in Dict")
                else:
                    key.comment_before = before
                    array[key] = value

    def _readValue(self, index: int) -> tuple[Key | None, Value]:
        key: str | None = None
        value: Value | None = None
        start = self._count
        match self._line[-1]:
            case 62:
                key = self._readKey(1)
                self._indent._key = key or index
                self._indent = self._indent.more()
                self._readln()
                value = Text()
                self._readText(value)
                self._indent = self._indent.less()
            case 93 if len(self._line) > 1 and self._line[-2] == 91:
                key = self._readKey(2)
                self._indent._key = key or index
                self._indent = self._indent.more()
                self._readln()
                value = List()
                self._readList(value)
                self._indent = self._indent.less()
            case 58:
                key = self._readKey(1)
                self._indent._key = key or index
                self._indent = self._indent.more()
                self._readln()
                value = Dict()
                self._readDict(value)
                self._indent = self._indent.less()
        if value is None:
            self._errors_add("unrecognized line")
            return (key, Text())  # error means value is irrelevant
        value.comment_after = self._readComment()
        value.starting_line = start
        return (key, value)
