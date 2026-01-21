from collections.abc import Mapping
from io import BytesIO
from time import perf_counter_ns
from typing import NamedTuple, Any, Self

from alacs import Memory, File, Encoded, Comment
import alacs.yaml
import ruamel.yaml
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.scanner import ScannerError


class FileSeparated(NamedTuple):
    alacs: File
    python: dict[str, str | list | dict]
    comments: list[str]
    yaml: bytes


class StealComments(alacs.yaml.YAML):
    def __init__(self):
        super().__init__()
        self.comments = list[str]()

    def encode(self, alacs: File) -> BytesIO:
        self.comments.clear()
        return super().encode(alacs)

    def _comment(self, indent: bytes, prefix: bytes, alacs: Comment | None) -> None:
        super()._comment(indent, prefix, alacs)
        if alacs is not None:
            if not indent and prefix == b"!":
                before= f"#{prefix.decode()}"
            else:
                before =  f"#{len(indent)}{prefix.decode()}"
            for line in alacs:
                if isinstance(line, memoryview):
                    line = line.tobytes()
                self.comments.append(f"{before}{line.decode()}")


class Timer:
    def __init__(self, denominator: "Timer|None" = None):
        self.total = 0
        self.count = 0
        self.start = 0
        self.denom = denominator

    def __enter__(self):
        self.start = perf_counter_ns()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.total += perf_counter_ns() - self.start
        self.count += 1

    @property
    def avg(self) -> float:
        return self.total / self.count if self.count else 0

    @property
    def mul(self) -> float:
        denom = self.denom
        if denom is None:
            return 0
        denom = denom.avg
        if denom == 0:
            return 0
        return round(self.avg / denom, 2)


class TimedMemory:
    def __init__(self):
        self.python_timer = Timer()
        self.file_timer = Timer()
        self.encode_timer = Timer()
        self.decode_timer = Timer()
        self.memory = Memory()
        self.steal = StealComments()

    def python(self, file: File) -> dict:
        with self.python_timer:
            return self.memory.python(file)

    def file(self, mapping: Mapping) -> File:
        with self.file_timer:
            return self.memory.file(mapping)

    def encode(self, file: File) -> memoryview:
        with self.encode_timer:
            return self.memory.encode(file)

    def decode(self, alacs: Encoded) -> File:
        with self.decode_timer:
            return self.memory.decode(alacs)

    def timers(self) -> None:
        print("   ALACS")
        print(f"\tencode = {self.encode_timer.avg}")
        print(f"\tdecode = {self.decode_timer.avg}")
        print(f"\tpython = {self.python_timer.avg}")
        print(f"\t  file = {self.file_timer.avg}")

    def separated(self, file: File) -> FileSeparated:
        python = self.python(file)
        yaml = self.steal.encode(file).getvalue()
        return FileSeparated(file, python, self.steal.comments, yaml)


class TimedRuamel:
    def __init__(self, memory: TimedMemory):
        self.alacs_timer = Timer()
        self.dump_timer = Timer(memory.encode_timer)
        self.load_timer = Timer(memory.decode_timer)
        self.buffer = alacs.yaml.YAML()
        self.ruamel = ruamel.yaml.YAML(typ="rt")
        self.ruamel.indent(mapping=2, sequence=4, offset=2)
        if self.preserves(b"comment", b"{}\n#comment"):
            raise ValueError("ruamel fixed after empty bug")


    def load(self, value: bytes | None) -> Any:
        if value is not None:
            self.buffer.seek(0)
            self.buffer.truncate()
            self.buffer.write(value)
        self.buffer.seek(0)
        return self.ruamel.load(self.buffer)

    def dump(self, any: Any) -> Self:
        self.buffer.seek(0)
        self.buffer.truncate()
        self.ruamel.dump(any, self.buffer)
        return self

    def __bytes__(self) -> bytes:
        self.buffer.seek(0)
        return self.buffer.getvalue()

    def preserves(self, mark: bytes, value: bytes) -> bool:
        return mark in bytes(self.dump(self.load(value)))

    def _load_file(self) -> CommentedMap:
        try:
            with self.load_timer:
                result = self.load(None)
        except ScannerError:
            print(bytes(self).decode())
            raise
        if not isinstance(result, CommentedMap):
            raise AssertionError(f"expected CommentedMap, got: {type(result)}")
        return result

    def roundtrip(self, file: CommentedMap) -> CommentedMap:
        with self.dump_timer:
            self.dump(file)
        return self._load_file()

    def translate(self, file: File) -> CommentedMap:
        with self.alacs_timer:
            self.buffer.encode(file)
        return self._load_file()

    def timers(self) -> None:
        print("   ruamel.yaml RT")
        print(f"\t  dump = {self.dump_timer.avg}  ({self.dump_timer.mul})")
        print(f"\t  load = {self.load_timer.avg}  ({self.load_timer.mul})")
        print(f"\t trans = {self.alacs_timer.avg}")
