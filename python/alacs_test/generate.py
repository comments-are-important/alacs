from random import randrange, choice, choices
from alacs import Comment, Text, List, Dict, Value, File, Key, Indent

bools = (False, True)
ascii = b"\t" + bytes(it for it in range(32, 127))


class Random:
    "single thread only"

    def __init__(self) -> None:
        self.deepest = 6
        self.widest = 8
        self.key = ascii
        self.comment = ascii
        self.text = ascii
        self.indent = Indent(b"")

    def _comment(self, kind: str) -> Comment:
        result = Comment(f"{self.indent.keys()} {kind}")
        for loop in range(randrange(3)):
            result.append(bytes(choices(self.comment, k=randrange(80))))
        if len(result) == 1 and not result[0]:
            result.clear()
        return result

    def _list(self, array: List, depth: int) -> List:
        if depth < randrange(self.deepest):
            self.indent = self.indent.more()
            for key in range(randrange(self.widest)):
                self.indent._key = key
                array.append(self._value(depth))
            self.indent = self.indent.less()
        if not array:
            array.append(Text(b"value"))
        if choice(bools):
            array.comment_after = self._comment("after")
        if choice(bools):
            array.comment_intro = self._comment("intro")
        return array

    def _dict_entries(self, array: Dict | File, depth: int) -> None:
        if depth < randrange(self.deepest):
            self.indent = self.indent.more()
            for loop in range(randrange(self.widest)):
                key = Key(bytes(choices(self.key, k=randrange(20))).decode())
                self.indent._key = key
                if choice(bools):
                    key.blank_line_before = True
                if choice(bools):
                    key.comment_before = self._comment("before")
                array[key] = self._value(depth)
            self.indent = self.indent.less()
        if not array:
            array[Key("key")] = Text(b"value")
        if choice(bools):
            array.comment_intro = self._comment("intro")

    def _dict(self, array: Dict, depth: int) -> Dict:
        self._dict_entries(array, depth)
        if choice(bools):
            array.comment_after = self._comment("after")
        return array

    def _value(self, depth: int) -> Value:
        match randrange(3):
            case 0:
                return self._dict(Dict(), depth + 1)
            case 1:
                return self._list(List(), depth + 1)
            case 2:
                text = Text()
                for loop in range(randrange(3)):
                    text.append(bytes(choices(self.text, k=randrange(80))))
                if len(text) == 1 and not text[0]:
                    text.clear()
                return text
        raise RuntimeError("impossible randrange case")

    def file(self) -> File:
        self.indent = self.indent.zero()
        file = File()
        if choice(bools):
            file.hashbang = self._comment("hashbang")
        self._dict_entries(file, 0)
        return file
