from io import BytesIO
from . import File, Dict, List, Text, Comment, Value, Encoded

__all__ = ["YAML"]


class YAML(BytesIO):
    """Produces YAML that is not particularly aesthetically pleasing.

    This class prioritizes simple code that preserves all the input. No attempt is made
    to make the output look nice. A load+dump cycle using `ruamel.yaml` round-trip will
    clean things up a bit without losing the comments."""

    def __init__(self):
        self._scratch = list[Encoded]()

    def encode(self, alacs: File) -> bytes:
        self.seek(0)
        self.truncate()
        self._comment(b"#!", alacs.hashbang)
        self.write(b"--- ")
        self._dict(b"", alacs)
        self._comment(b"#0a:", alacs.comment_after)
        self.write(b"...")
        return self.getvalue()

    def _utf8(self, indent: bytes, alacs: list[Encoded]) -> None:
        for line in alacs:
            self.write(indent)
            self.write(line)
            self.write(b"\n")

    def _comment(self, indent: bytes, alacs: Comment | None) -> None:
        if alacs is not None:
            alacs.normalize(self._scratch)
            self._utf8(indent, alacs)

    def _value(self, indent: bytes, alacs: Value) -> None:
        match alacs:
            case Text():
                self._text(indent, alacs)
            case List():
                self._list(indent, alacs)
            case Dict():
                self._dict(indent, alacs)
            case _:
                raise ValueError(f"unexpected type: {type(alacs)}")
        self._comment(b"#%da:" % len(indent), alacs.comment_after)

    def _text(self, indent: bytes, value: Text) -> None:
        value.normalize(self._scratch)
        if value and not value[-1]:
            self.write(b"|1+\n")
            self._utf8(indent, value[:-1])
        else:
            self.write(b"|1-\n")
            self._utf8(indent, value)

    def _list(self, indent: bytes, alacs: List) -> None:
        self.write(b"!!seq\n")
        self._comment(b"#%di:" % len(indent), alacs.comment_intro)
        if not alacs:
            self.write(indent)
            self.write(b"[]\n")
            return
        more = indent + b" "
        for value in alacs:
            self.write(indent)
            self.write(b"- ")
            self._value(more, value)

    def _dict(self, indent: bytes, alacs: Dict) -> None:
        self.write(b"!!map\n")
        self._comment(b"#%di:" % len(indent), alacs.comment_intro)
        if not alacs:
            self.write(indent)
            self.write(b"{}\n")
            return
        more = indent + b" "
        for key, value in alacs.items():
            if key.blank_line_before:
                self.write(b"#b\n")
            self._comment(b"#%dk:" % len(indent), key.comment_before)
            self.write(indent)
            self.write(b'"')
            key = key.replace("\\", r"\\").replace('"', r"\"").replace("\t", r"\t")
            self.write(key.encode())
            self.write(b'": ')
            self._value(more, value)
