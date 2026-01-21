from io import BytesIO
from . import File, Dict, List, Text, Comment, Value, Key, Encoded

__all__ = ["YAML"]


class YAML(BytesIO):
    """Produces YAML that is not particularly aesthetically pleasing.

    This class prioritizes simple code that preserves all the input. No attempt is made
    to make the output look nice. A load+dump cycle using `ruamel.yaml` round-trip will
    clean things up a bit without losing the comments.

    Note that the order of comments in the YAML is differs to accommodate ruamel.yaml
    round trip losing comments in various places:
     - (between key and value)[https://sourceforge.net/p/ruamel-yaml/tickets/418/#4a67]
     - (at end of file)[https://sourceforge.net/p/ruamel-yaml/tickets/451/]"""

    def __init__(self):
        self._scratch = list[Encoded]()
        self._blank = Comment()

    def encode(self, alacs: File) -> BytesIO:
        self.seek(0)
        self.truncate()
        self.write(b'--- !map\n')
        self._comment(b"", b"!", alacs.hashbang)
        self._comment(b"", b"i:", alacs.comment_intro)
        self._dict(b"", False, alacs)
        self.write(b'...\n')
        return self

    def _utf8(self, indent: bytes, prefix: bytes, alacs: list[Encoded]) -> None:
        for line in alacs:
            self.write(indent)
            self.write(prefix)
            self.write(line)
            self.write(b"\n")

    def _comment(self, indent: bytes, prefix: bytes, alacs: Comment | None) -> None:
        if alacs is not None:
            marked = b"#" if prefix == b"!" else b"#%d" % len(indent)
            alacs.normalize(self._scratch)
            self._utf8(marked, prefix, alacs)

    def _value(self, indent: bytes, key: Key | bool, alacs: Value) -> None:
        match alacs:
            case Text():
                self._comment(indent, b"a:", alacs.comment_after)
                self._text(indent, key, alacs)
            case List():
                self._comment(indent, b"i:", alacs.comment_intro)
                self._comment(indent, b"a:", alacs.comment_after)
                self._list(indent, key, alacs)
            case Dict():
                self._comment(indent, b"i:", alacs.comment_intro)
                self._comment(indent, b"a:", alacs.comment_after)
                self._dict(indent, key, alacs)
            case _:
                raise ValueError(f"unexpected type: {type(alacs)}")

    def _text(self, indent: bytes, key: Key | bool, value: Text) -> None:
        value.normalize(self._scratch)
        if value and not value[-1]:
            self._key(indent, key, b"|2+")
            self._utf8(indent, b"  ", value[:-1])
        else:
            self._key(indent, key, b"|2-")
            self._utf8(indent, b"  ", value)

    def _list(self, indent: bytes, key: Key | bool, alacs: list[Value]) -> None:
        if not alacs:
            self._key(indent, key, b"[]")
        else:
            self._key(indent, key, b"")
            more = indent + b" "
            for value in alacs:
                self._value(more, True, value)

    def _dict(self, indent: bytes, key: Key | bool, alacs: dict[Key, Value]) -> None:
        if not alacs:
            self._key(indent, key, b"{}")
        else:
            self._key(indent, key, b"")
            more = indent + b" "
            for key, value in alacs.items():
                if key.blank_line_before:
                    self._comment(more, b"b", self._blank)
                self._comment(more, b"k:", key.comment_before)
                self._value(more, key, value)

    def _key(self, indent: bytes, key: Key | bool, end: bytes) -> None:
        self.write(indent)
        match key:
            case False:
                self.write(end)
            case True:
                self.write(b"-")
                if end:
                    self.write(b" ")
                    self.write(end)
            case Key():
                value = key.replace("\\", r"\\").replace('"', r"\"").replace("\t", r"\t")
                self.write(b'"')
                self.write(value.encode())
                self.write(b'":')
                if end:
                    self.write(b" ")
                    self.write(end)
            case _:
                raise ValueError(f"unexpected type: {type(key)}")
        self.write(b"\n")
