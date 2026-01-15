from abc import ABC, abstractmethod
from collections import UserString
from collections.abc import Mapping, Sequence
from io import BytesIO, StringIO
from typing import Any, ClassVar, TypeAlias

# multiple inheritance (from builtins in particular) means that __slots__ and __init__
# must be written as below to avoid TypeError about instance lay-out conflict.

__all__ = [
    "Encoded",
    "String",
    "UTF8",
    "Comment",
    "Value",
    "Text",
    "Array",
    "List",
    "Key",
    "Dict",
    "File",
    "Indent",
    "Memory",
]

Encoded: TypeAlias = bytes | bytearray | memoryview
String: TypeAlias = str | UserString


class UTF8(list[Encoded]):
    __slots__ = ()

    def __init__(self, *lines: Encoded | String):
        super().__init__(lines)  # type: ignore
        for index, line in enumerate(self):
            match line:
                case str() | UserString():
                    self[index] = line.encode()

    def __bytes__(self) -> bytes:
        return b'\n'.join(self)

    def __str__(self) -> str:
        return bytes(self).decode()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}={str(self)}>"

    def normalize(self, scratch: list[Encoded] | None) -> None:
        if 1 == len(self) and 0 == len(self[0]):
            self.clear()  # `[]` is more "True"ly empty than `[b'']`
        else:
            if scratch is None:
                scratch = list[Encoded]()
            else:
                scratch.clear()
            for index in range(len(self) - 1, -1, -1):
                chunk = self[index]
                if not isinstance(chunk, memoryview):
                    if b"\n" not in chunk:
                        continue
                    chunk = memoryview(chunk)
                start = len(chunk) - 1
                while 0 <= start and 10 != chunk[start]:
                    start -= 1
                if 0 <= start:
                    scratch.append(chunk[start + 1 :])
                    limit = start
                    start -= 1
                    while start >= 0:
                        if 10 == chunk[start]:
                            scratch.append(chunk[start + 1 : limit])
                            limit = start
                        start -= 1
                    scratch.append(chunk[:limit])
                    scratch.reverse()
                    self[index : index + 1] = scratch
                    scratch.clear()


# =====================================================================================


class Comment(UTF8):
    starting_line: int  # = 0
    __slots__ = ("starting_line",)

    def __init__(self, *lines: Encoded | String):
        super().__init__(*lines)
        self.starting_line = 0


class Value(ABC):
    starting_line: int  # = 0
    comment_after: Comment | None  # = None
    __slots__ = ()


class Text(UTF8, Value):
    __slots__ = ("starting_line", "comment_after")

    def __init__(self, *lines: Encoded | String):
        super().__init__(*lines)
        self.starting_line = 0
        self.comment_after = None


class Array(Value, ABC):
    comment_intro: Comment | None  # = None
    __slots__ = ()

    @abstractmethod
    def __len__(self) -> int:
        pass


class List(list[Value], Array):
    __slots__ = ("starting_line", "comment_after", "comment_intro")

    def __init__(self, *values: Value):
        super().__init__(values)
        self.starting_line = 0
        self.comment_after = None
        self.comment_intro = None


class Key(str):
    blank_line_before: bool  # = False
    comment_before: Comment | None  # = None
    __slots__ = ("blank_line_before", "comment_before")

    def __init__(self, handled_by_str_new_but_here_for_type_hint: Any):
        if "\n" in self:
            raise ValueError("newline in key")
        self.blank_line_before = False
        self.comment_before = None


class Dict(dict[Key, Value], Array):
    __slots__ = ("starting_line", "comment_after", "comment_intro")

    def __init__(self, **values: Value):
        super().__init__((Key(k), v) for k, v in values.items())
        self.starting_line = 0
        self.comment_after = None
        self.comment_intro = None


class File(Dict):
    hashbang: Comment | None  # = None
    __slots__ = ("hashbang",)

    def __init__(self, **values: Value):
        super().__init__(**values)
        self.hashbang = None


# ========================================================================= ThreadLocal


class Indent:
    __slots__ = ("_bytes", "_more", "_less", "_key")

    def __init__(self, value: bytes):
        if value.count(b"\t") != len(value):
            raise AssertionError("indent must be tab chars only")
        self._bytes = value
        self._more: Indent | None = None
        self._less: Indent | None = None
        self._key: Any = None

    def more(self) -> "Indent":
        result = self._more
        if result is None:
            result = self._more = Indent(self._bytes + b"\t")
            result._less = self
        return result

    def less(self) -> "Indent":
        result = self._less
        if result is None:
            raise AssertionError("indent can't go negative")
        return result

    def keys(self) -> str:
        if self._less is None:
            return "" if self._key is None else f"{self._key}"
        match self._key:
            case None:
                return ""
            case str(key):
                return f"{self.less().keys()}.{key}"
            case key:
                return f"{self.less().keys()}[{key}]"

    def zero(self) -> "Indent":
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
    empty: ClassVar[memoryview] = memoryview(b"")
    __slots__ = (
        "_scratch",
        "_errors",
        "_indent",
        "_count",
        "_write",
        "_parse",
        "_next",
        "_line",
        "_tabs",
        "_assign",
    )

    def __init__(self):
        super().__init__()
        self._scratch = list[Encoded]()
        self._errors = list[str]()
        self._indent: Indent = Indent(b"")
        self._count: int = 0
        self._write = BytesIO()
        self._parse = Memory.empty
        self._next: int = -1
        self._line = Memory.empty
        self._tabs: int = -1
        self._assign: int = -1

    # -------------------------------------------------------------------------- errors

    def _error(self, message: str) -> str:
        match self._errors:
            case []:
                return message
            case _:
                return f"{message}:\n\t{'\n\t'.join(self._errors)}"

    def _errors_add(self, *parts: Any) -> None:
        message = StringIO()
        if self._count:
            message.write(f"#{self._count} ")
        message.write(self._indent.keys())
        if parts:
            message.write(":")
            for part in parts:
                message.write(" ")
                message.write(str(part))
        self._errors.append(message.getvalue())

    # ----------------------------------------------------------------------- to python

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
                    raise ValueError(
                        self._error("argument is or contains illegal non-`Value` data")
                    )
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
        return None

    # --------------------------------------------------------------------- from python

    def file(self, mapping: Mapping) -> File:
        """Convert a simple Python `dict` (any mapping) to a `File`.

        Returns deep copy except bytes/bytearray/memoryview are shared
        (even though some of those are mutable)."""
        self._errors.clear()
        self._indent = self._indent.zero()
        try:
            match self._value(mapping):
                case _ if self._errors:
                    raise ValueError(
                        self._error(
                            "argument contains data that can't be converted to `Value`"
                        )
                    )
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
                result.normalize(self._scratch)
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
        return None

    # -------------------------------------------------------------------------- encode

    def encode(self, file: File) -> memoryview:
        """result must be `release`d - suggest use `with`."""
        self._errors.clear()
        self._indent = self._indent.zero()
        try:
            self._count = 0
            self._write.seek(0)
            self._write.truncate()
            self._writeComment(b"#!", file.hashbang)
            self._writeDict(file)
            self._writeComment(b"#", file.comment_after)
            if self._errors:
                raise ValueError(
                    self._error("argument is or contains illegal non-`Value` data")
                )
            return self._write.getbuffer()
        finally:
            self._scratch.clear()
            self._errors.clear()
            self._indent = self._indent.zero()

    def _writeIndent(self) -> None:
        if self._count:
            self._write.write(b"\n")
            self._count += 1
        else:
            self._count = 1
        self._write.write(self._indent._bytes)

    def _writeComment(self, marker: bytes, comment: Comment | None) -> None:
        if comment is not None:
            self._writeIndent()
            self._write.write(marker)
            comment.starting_line = self._count
            comment.normalize(self._scratch)
            if comment:
                self._write.write(comment[0])
                self._indent = self._indent.more()
                for index in range(1, len(comment)):
                    self._writeIndent()
                    self._write.write(comment[index])
                self._indent = self._indent.less()

    def _shortList(self, text: Text) -> bool:
        """check if encoding should use short List item syntax."""
        text.normalize(self._scratch)
        match len(text):
            case 0:
                return True
            case 1:
                return text[0][0] not in b"\t#<>[]{}/="
        return False

    def _writeList(self, array: List) -> None:
        self._writeComment(b"#", array.comment_intro)
        for index, value in enumerate(array):
            self._indent._key = index
            self._writeIndent()
            value.starting_line = self._count
            match value:
                case Text():
                    if not self._shortList(value):
                        self._write.write(b"<>")
                        self._indent = self._indent.more()
                        for line in value:
                            self._writeIndent()
                            self._write.write(line)
                        self._indent = self._indent.less()
                    elif value:
                        self._write.write(value[0])
                case List():
                    self._write.write(b"[]")
                    self._indent = self._indent.more()
                    self._writeList(value)
                    self._indent = self._indent.less()
                case Dict():
                    self._write.write(b"{}")
                    self._indent = self._indent.more()
                    self._writeDict(value)
                    self._indent = self._indent.less()
                case _:
                    self._errors_add("value is", type(value))
            self._writeComment(b"#", value.comment_after)

    def _shortDict(self, key: Key, text: Text) -> bool:
        """check if encoding should use short Dict entry syntax."""
        text.normalize(self._scratch)
        if len(text) > 1:
            return False
        if not key:
            return True
        if key[0] in "\t#<>[]{}/":
            return False
        if "=" in key:
            return False
        return True

    def _writeDict(self, array: Dict) -> None:
        self._writeComment(b"#", array.comment_intro)
        for key, value in array.items():
            self._indent._key = key
            if not isinstance(key, Key):
                self._errors_add("key is", type(key))
                continue
            if key.blank_line_before:
                self._writeIndent()
            self._writeComment(b"//", key.comment_before)
            self._writeIndent()
            value.starting_line = self._count
            match value:
                case Text():
                    if not self._shortDict(key, value):
                        self._write.write(b"<")
                        self._write.write(key.encode())
                        self._write.write(b">")
                        self._indent = self._indent.more()
                        for line in value:
                            self._writeIndent()
                            self._write.write(line)
                        self._indent = self._indent.less()
                    else:
                        self._write.write(key.encode())
                        self._write.write(b"=")
                        if value:
                            self._write.write(value[0])
                case List():
                    self._write.write(b"[")
                    self._write.write(key.encode())
                    self._write.write(b"]")
                    self._indent = self._indent.more()
                    self._writeList(value)
                    self._indent = self._indent.less()
                case Dict():
                    self._write.write(b"{")
                    self._write.write(key.encode())
                    self._write.write(b"}")
                    self._indent = self._indent.more()
                    self._writeDict(value)
                    self._indent = self._indent.less()
                case _:
                    self._errors_add("value is", type(value))
            self._writeComment(b"#", value.comment_after)

    # -------------------------------------------------------------------------- decode

    def decode(self, alacs: bytes) -> File:
        self._errors.clear()
        self._indent = self._indent.zero()
        try:
            self._count = 0
            self._parse = memoryview(alacs)
            self._next = 0
            self._readln()
            file = File()
            if len(self._line) > 1 and self._line[0] == 35 and self._line[1] == 33:
                file.hashbang = self._readComment(2)
            self._readDict(file)
            if self._errors:
                raise ValueError(self._error("parse errors"))
            return file
        finally:
            self._scratch.clear()
            self._errors.clear()
            self._indent = self._indent.zero()
            self._parse = self._line = Memory.empty

    def _readln(self) -> bool:
        index = self._next
        limit = len(self._parse)
        if index >= limit:
            if self._line is not Memory.empty:
                self._count += 1
                self._line = Memory.empty
                self._tabs = self._assign = -1
            return False
        byte = self._parse[index]
        while byte == 9:
            index += 1
            if index >= limit:
                byte = 10
                break
            byte = self._parse[index]
        self._tabs = index - self._next
        self._assign = -1
        while byte != 10:
            if byte == 61 and self._assign < 0:
                self._assign = index - self._next
            index += 1
            if index >= limit:
                break
            byte = self._parse[index]
        self._line = self._parse[self._next : index]
        self._count += 1
        self._next = index + 1
        return True

    def _readExcess(self) -> None:
        if self._tabs > len(self._indent):
            message = StringIO(f"#{self._count}: excess indentation")
            count = 1
            while self._readln() and self._tabs > len(self._indent):
                count += 1
            if count > 1:
                message.write(f" ({count} lines)")
            self._errors_add(message.getvalue())

    def _readComment(self, start: int) -> Comment:
        comment = Comment(self._line[start:])
        comment.starting_line = self._count
        indent = len(self._indent) + 1
        while self._readln() and self._tabs >= indent:
            comment.append(self._line[indent:])
        return comment

    def _readText(self) -> Text:
        text = Text()
        text.starting_line = self._count
        indent = len(self._indent) + 1
        while self._readln() and self._tabs >= indent:
            text.append(self._line[indent:])
        if len(text) == 1 and len(text[0]) == 0:
            text.clear()
        return text

    def _readList(self, array: List) -> None:
        self._readExcess()
        indent = len(self._indent)
        if self._tabs < indent:
            return
        if len(self._line) > indent and self._line[indent] == 35:
            array.comment_intro = self._readComment(indent + 1)
        self._readExcess()
        while self._tabs == indent:
            size = len(self._line) - indent
            if size < 0:
                raise AssertionError(f"""impossible math:
                    len(line) = {len(self._line)}
                    indent    = {indent}
                    tabs      = {self._tabs}""")
            value: Value | None = None
            match 10 if size == 0 else self._line[indent]:
                case 10:
                    value = Text()
                    self._readln()
                case 35:
                    self._errors_add("unattached comment")
                    self._readComment(indent)
                case 47:
                    self._errors_add("key comment in list context")
                    self._readComment(indent)
                case 60:
                    if size != 2 or self._line[-1] != 62:
                        self._errors_add("malformed text opening")
                    else:
                        value = self._readText()
                case 91:
                    if size != 2 or self._line[-1] != 93:
                        self._errors_add("malformed linear array opening")
                    else:
                        value = List()
                        self._readln()
                        self._indent = self._indent.more()
                        self._readList(value)
                        self._indent = self._indent.less()
                case 123:
                    if size != 2 or self._line[-1] != 125:
                        self._errors_add("malformed associative array opening")
                    else:
                        value = Dict()
                        self._readln()
                        self._indent = self._indent.more()
                        self._readDict(value)
                        self._indent = self._indent.less()
                case _:
                    value = Text(self._line[indent:])
                    self._readln()
            if value is not None:
                if self._tabs == indent:
                    if len(self._line) > indent and self._line[indent] == 35:
                        value.comment_after = self._readComment(indent + 1)
                array.append(value)
            self._readExcess()

    def _readDict(self, array: Dict) -> None:
        self._readExcess()
        indent = len(self._indent)
        if self._tabs < indent:
            return
        if len(self._line) > indent and self._line[indent] == 35:
            array.comment_intro = self._readComment(indent + 1)
        entries = 0
        blank = 0
        comment: Comment | None = None
        self._readExcess()
        while self._tabs == indent:
            size = len(self._line) - indent
            if size < 0:
                raise AssertionError(f"""impossible math:
                    len(line) = {len(self._line)}
                    indent    = {indent}
                    tabs      = {self._tabs}""")
            if size == 0:
                if comment:
                    self._errors_add("blank line must precede key comment")
                elif blank:
                    self._errors_add("more than one blank line")
                else:
                    blank = self._count
                self._readln()
                continue
            key: Key | None = None
            value: Value | None = None
            match self._line[indent]:
                case 35:
                    if isinstance(array, File) and not array.comment_after:
                        array.comment_after = self._readComment(1)
                    else:
                        self._errors_add("illegal position for comment")
                        self._readComment(indent + 1)
                case 47:
                    if size < 2 or self._line[indent + 1] != 47:
                        self._errors_add("malformed key comment")
                        self._readComment(indent)
                    elif comment:
                        self._errors_add("more than one key comment")
                    else:
                        comment = self._readComment(indent + 2)
                case 60:
                    if size < 2 or self._line[-1] != 62:
                        self._errors_add("malformed text opening")
                    else:
                        key = Key(self._line[indent + 1 : -1].tobytes().decode())
                        value = self._readText()
                case 91:
                    if size < 2 or self._line[-1] != 93:
                        self._errors_add("malformed linear array opening")
                    else:
                        key = Key(self._line[indent + 1 : -1].tobytes().decode())
                        self._readln()
                        value = List()
                        self._indent = self._indent.more()
                        self._readList(value)
                        self._indent = self._indent.less()
                case 123:
                    if size < 2 or self._line[-1] != 125:
                        self._errors_add("malformed associative array opening")
                    else:
                        key = Key(self._line[indent + 1 : -1].tobytes().decode())
                        self._readln()
                        value = Dict()
                        self._indent = self._indent.more()
                        self._readDict(value)
                        self._indent = self._indent.less()
                case _:
                    if self._assign < 0:
                        self._errors_add("malformed `key=value` association")
                    else:
                        key = Key(self._line[indent : self._assign].tobytes().decode())
                        value = Text(self._line[self._assign + 1 :])
                        self._readln()
            if value is not None:
                if self._tabs == indent:
                    if len(self._line) > indent and self._line[indent] == 35:
                        value.comment_after = self._readComment(indent + 1)
                if key is None:
                    raise AssertionError("association needs both key and value")
                array[key] = value
                if blank:
                    key.blank_line_before = True
                    blank = False
                if comment:
                    key.comment_before = comment
                    comment = None
                entries += 1
                if len(array) != entries:
                    self._errors_add(f"duplicate key: {key}")
            elif key is not None:
                raise AssertionError("association needs both key and value")
            self._readExcess()
        if comment or blank:
            self._errors_add("unclaimed key comment or blank line")
