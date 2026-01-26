import re
from collections import UserString
from typing import Any, TypeAlias, ClassVar, ContextManager
import unittest
import alacs_test
from alacs import ALACS, UTF8, Comment, Text, Key, File, List, Dict
from alacs.pointer import Indent
from alacs.yaml import YAML

ExType: TypeAlias = type[BaseException]

# focus is on filling in gaps left  by the timing script in alacs_test.__main__
# goal is to test all error branches to get 100% coverage of alacs.__init__


class BadFile(File):
    def __init__(self, message: str):
        super().__init__()
        self.message = message


class Impossible(ALACS):
    """a broken subclass that returns an impossible result from select methods."""

    def __init__(self, result: Any):
        super().__init__()
        self.impossible_result = result

    def _python(self, _):
        # self.python(File) calls this and validates the result.
        # actual code never returns None without also adding an error,
        # and always returns a dict when called on a File.
        return self.impossible_result

    def _value(self, _):
        # self.file(Mapping) calls this and validates the result
        # actual code never returns None without also adding an error,
        # and always returns a File when called on a Mapping.
        return self.impossible_result


class TestCase(unittest.TestCase):
    def assertRaisesExactly(self, ex: ExType, literal: str) -> ContextManager:
        pattern = re.compile(f"\\A{re.escape(literal)}\\Z")
        manager = self.assertRaisesRegex(ex, pattern)
        assert isinstance(manager, ContextManager)
        return manager

    def assertValueError(self, literal: str) -> ContextManager:
        return self.assertRaisesExactly(ValueError, literal)

    def assertAssertionError(self, literal: str) -> ContextManager:
        return self.assertRaisesExactly(AssertionError, literal)

    def illegalEllipsisKey(self, message: str, include_line=False) -> BadFile:
        line = "#1: " if include_line else ""
        result = BadFile(f"{message}:\n\t{line}key is <class 'ellipsis'> @/~...")
        result[...] = ...  # type: ignore
        return result

    def illegalEllipsisValue(self, message: str, include_line=False) -> BadFile:
        line = "#1: " if include_line else ""
        result = BadFile(f"{message}:\n\t{line}value is <class 'ellipsis'> @/k")
        result[Key("k")] = ...  # type: ignore
        return result

    def illegalEllipsisItem(self, message: str, include_line=False) -> BadFile:
        line = "#2: " if include_line else ""
        result = BadFile(f"{message}:\n\t{line}value is <class 'ellipsis'> @/k/0")
        result[Key("k")] = List(...)  # type: ignore
        return result


class TestUTF8(TestCase):
    def test_repr(self):
        self.assertEqual(repr(UTF8()), "UTF8()")
        self.assertEqual(repr(Comment(UserString("c"))), "Comment(b'c')")
        self.assertEqual(repr(Text("1", "2")), r"Text(b'1\n2')")

    def test_normalize(self):
        text = Text(b"1\n2\n3", bytearray(b"4\n5\n6"), memoryview(b"7\n8\n9"))
        self.assertEqual(len(text), 3)
        text.normalize(None)
        self.assertEqual(len(text), 9)


class TestKey(TestCase):
    def test_illegal(self):
        with self.assertValueError("newline in key"):
            Key("\n")
        with self.assertValueError("newline in key"):
            Key("_\n")
        with self.assertValueError("newline in key"):
            Key("\n_")
        with self.assertValueError("newline in key"):
            Key("_\n_")


class TestIndent(TestCase):
    def test_illegal(self):
        with self.assertAssertionError("indent must be tab chars only"):
            Indent(b" ")

    def test_negative(self):
        with self.assertAssertionError("indent can't go negative"):
            Indent(b"").less()

    def test_zero(self):
        indents = list[Indent]()
        indents.append(Indent(b""))
        indents.append(indents[-1].more())
        indents.append(indents[-1].more())
        indents.append(indents[-1].more())
        for index, indent in enumerate(indents):
            indent.key = index
        self.assertEqual(repr(indents[2]), "<Indent 2 @/0/1/2>")
        self.assertEqual(repr(indents[3]), "<Indent 3 @/0/1/2/3>")
        self.assertIs(indents[0], indents[2].zero())
        for index in range(len(indents)):
            self.assertIsNone(indents[index].key)


class TestYAML(TestCase):
    def assertEncoded(self, file: File, *lines: bytes) -> None:
        yaml = b"--- !map\n" + b"\n".join(lines) + b"\n...\n"
        self.assertEqual(YAML().encode(file).getvalue(), yaml)

    def test_empty_file(self):
        self.assertEncoded(File(), b"{}")

    def test_empty_arrays(self):
        self.assertEncoded(File(d=Dict(), l=List()), b'"d": {}', b'"l": []')

    def test_empty_text(self):
        self.assertEncoded(File(t=Text()), b'"t": |2-')

    def test_text_normal(self):
        self.assertEncoded(File(t=Text("one\ntwo")), b'"t": |2-\n  one\n  two')

    def test_text_tricky(self):
        self.assertEncoded(File(t=Text("\no\nt\n")), b'"t": |2+\n  \n  o\n  t')

    def test_bad_value(self):
        with self.assertValueError("unexpected type: <class 'ellipsis'>"):
            YAML()._value(b"", False, ...)  # type: ignore

    def test_bad_key(self):
        with self.assertValueError("unexpected type: <class 'ellipsis'>"):
            YAML()._key(b"", ..., b"")  # type: ignore


class TestMiscAndErrors(TestCase):
    def assertReprEval(self, code: str) -> None:
        self.assertEqual(repr(eval(code)), code)

    def test_text_repr(self):
        self.assertReprEval("Text()")
        self.assertReprEval("Text(after=Comment(b'a'))")
        self.assertReprEval("Text(b'')")
        self.assertReprEval("Text(b'',after=Comment(b'a'))")
        self.assertReprEval("Text(b'1')")
        self.assertReprEval("Text(b'1',after=Comment(b'a'))")
        self.assertReprEval(r"Text(b'1\n2')")
        self.assertReprEval(r"Text(b'1\n2',after=Comment(b'a'))")

    def test_list_repr(self):
        self.assertReprEval("List()")
        self.assertReprEval("List(Text(b'v'))")
        self.assertReprEval("List(intro=Comment(b'i'))")
        self.assertReprEval("List(Text(b'v'),intro=Comment(b'i'))")
        self.assertReprEval("List(intro=Comment(b'i'),after=Comment(b'a'))")
        self.assertReprEval("List(Text(b'v'),intro=Comment(b'i'),after=Comment(b'a'))")
        self.assertReprEval("List(Text(b'v'),after=Comment(b'a'))")
        self.assertReprEval("List(after=Comment(b'a'))")

    def test_dict_repr(self):
        self.assertReprEval("Dict()")
        self.assertReprEval("Dict(k=Text(b'v'))")
        self.assertReprEval("Dict(Comment(b'i'))")
        self.assertReprEval("Dict(Comment(b'i'),k=Text(b'v'))")
        self.assertReprEval("Dict(Comment(b'i'),Comment(b'a'))")
        self.assertReprEval("Dict(Comment(b'i'),Comment(b'a'),k=Text(b'v'))")
        self.assertReprEval("Dict(None,Comment(b'a'),k=Text(b'v'))")
        self.assertReprEval("Dict(None,Comment(b'a'))")

    def test_file_repr(self):
        self.assertReprEval("File()")
        self.assertReprEval("File(k=Text(b'v'))")
        self.assertReprEval("File(Comment(b'h'))")
        self.assertReprEval("File(Comment(b'h'),k=Text(b'v'))")
        self.assertReprEval("File(Comment(b'h'),Comment(b'i'))")
        self.assertReprEval("File(Comment(b'h'),Comment(b'i'),k=Text(b'v'))")
        self.assertReprEval("File(None,Comment(b'i'),k=Text(b'v'))")
        self.assertReprEval("File(None,Comment(b'i'))")

    def test_to_file(self):
        actual = File(Comment("h"), Dict(Comment("c"), k=Text("v")))
        expect = File(Comment("h"), Comment("c"), k=Text("v"))
        self.assertEqual(actual, expect)

    def test_to_dict(self):
        actual = File(Comment("h"), Comment("c"), k=Text("v"))
        expect = Dict(Comment("c"), k=Text("v"))
        self.assertEqual(Dict(actual), expect)

    def test_empty(self):
        message = "one two five"
        self.assertIs(ALACS()._error(message), message)

    def test_eq_ignores_comments(self):
        one = File(k=Text("t", after=Comment("one")))
        two = File(k=Text("t", after=Comment("two")))
        self.assertEqual(one, two)
        self.assertNotEqual(repr(one), repr(two))


class TestPython(TestCase):
    def test_impossible_none_no_error(self):
        with self.assertAssertionError("impossible: got None, but no error"):
            Impossible(None).python(File())

    def test_impossible_type(self):
        with self.assertAssertionError("impossible: got <class 'ellipsis'>"):
            Impossible(...).python(File())

    illegal: ClassVar[str] = "illegal non-`Value` data"

    def test_illegal_key(self):
        bad_file = self.illegalEllipsisKey(self.illegal)
        with self.assertValueError(bad_file.message):
            ALACS().python(bad_file)

    def test_illegal_value(self):
        bad_file = self.illegalEllipsisValue(self.illegal)
        with self.assertValueError(bad_file.message):
            ALACS().python(bad_file)


class TestFile(TestCase):
    def test_impossible_none_no_error(self):
        with self.assertAssertionError("impossible: got None, but no error"):
            Impossible(None).file({})

    def test_impossible_type(self):
        with self.assertAssertionError("impossible: got <class 'ellipsis'>"):
            Impossible(...).file({})

    def test_none_is_empty_text(self):
        self.assertEqual(File(k=Text()), ALACS().file({"k": None}))

    illegal: ClassVar[str] = "can't be converted to `Value`"

    def test_illegal_key(self):
        bad_file = self.illegalEllipsisKey(self.illegal)
        with self.assertValueError(bad_file.message):
            ALACS().file(bad_file)

    def test_illegal_value(self):
        bad_file = self.illegalEllipsisValue(self.illegal)
        with self.assertValueError(bad_file.message):
            ALACS().file(bad_file)

    def test_illegal_list_item(self):
        bad_file = self.illegalEllipsisItem(self.illegal)
        with self.assertValueError(bad_file.message):
            ALACS().file(bad_file)


class TestEncode(TestCase):
    def test_denormalized(self):
        text = Text("")
        text.comment_after = Comment()
        text.comment_after.append(b"")  # now it is not normalized
        with ALACS().encode(File(k=text)) as buffer:
            alacs = buffer.tobytes().decode()
            self.assertEqual(alacs, "k=\n#")

    illegal: ClassVar[str] = "illegal non-`Value` data"

    def test_illegal_key(self):
        bad_file = self.illegalEllipsisKey(self.illegal, True)
        with self.assertValueError(bad_file.message):
            ALACS().encode(bad_file)

    def test_illegal_value(self):
        bad_file = self.illegalEllipsisValue(self.illegal, True)
        with self.assertValueError(bad_file.message):
            ALACS().encode(bad_file)

    def test_illegal_list_item(self):
        bad_file = self.illegalEllipsisItem(self.illegal, True)
        with self.assertValueError(bad_file.message):
            ALACS().encode(bad_file)


class TestDecode(TestCase):
    def test_readln(self):
        alacs = ALACS()
        alacs._next = 0
        self.assertEqual(alacs._readln(), False)
        self.assertEqual(alacs._readln(), False)

    def test_lenient_text(self):
        self.assertEqual(ALACS().decode(b"<k>\n\t"), File(k=Text()))

    def assertParseError(self, literal: str) -> ContextManager:
        return self.assertValueError(f"parse errors:\n\t{literal}")

    def test_excess_root_one(self):
        with self.assertParseError("#1: excess indentation @/"):
            ALACS().decode(b"\tk=v\nk=v")

    def test_excess_dict_one(self):
        with self.assertParseError("#2: excess indentation @/o/"):
            ALACS().decode(b"{o}\n\t\tk=v\nk=v")

    def test_excess_root_more(self):
        with self.assertParseError("#1: 3 lines excess indentation @/"):
            ALACS().decode(b"\tk=v\n\tk=v\n\tk=v\nk=v")

    def test_excess_list_one(self):
        with self.assertParseError("#2: excess indentation @/k/"):
            ALACS().decode(b"[k]\n\t\tx")

    def test_malformed_text_in_dict(self):
        with self.assertParseError("#1: malformed text opening @"):
            ALACS().decode(b"<foo")

    def test_malformed_text_in_list(self):
        with self.assertParseError("#2: malformed text opening @/key/0"):
            ALACS().decode(b"[key]\n\t<foo")

    def test_malformed_list_in_dict(self):
        with self.assertParseError("#1: malformed linear array opening @"):
            ALACS().decode(b"[foo")

    def test_malformed_list_in_list(self):
        with self.assertParseError("#2: malformed linear array opening @/key/0"):
            ALACS().decode(b"[key]\n\t[foo")

    def test_malformed_dict_in_dict(self):
        with self.assertParseError("#1: malformed associative array opening @"):
            ALACS().decode(b"{foo")

    def test_malformed_dict_in_list(self):
        with self.assertParseError("#2: malformed associative array opening @/key/0"):
            ALACS().decode(b"[key]\n\t{foo")

    def test_unattached_comment_in_list(self):
        with self.assertParseError("#4: unattached comment @/key/1"):
            ALACS().decode(b"[key]\n\tvalue\n\t#attached\n\t#unattached")

    def test_key_comment_in_list_context(self):
        with self.assertParseError("#2: key comment in list context @/key/0"):
            ALACS().decode(b"[key]\n\t//comment")

    def test_illegal_comment_position_in_dict(self):
        with self.assertParseError("#3: illegal position for comment @"):
            ALACS().decode(b"foo=bar\n#attached\n#illegal")

    def test_malformed_key_comment(self):
        with self.assertParseError("#1: malformed key comment @"):
            ALACS().decode(b"/comment")

    def test_multiple_key_comments(self):
        with self.assertParseError("#2: more than one key comment @"):
            ALACS().decode(b"//comment1\n//comment2\nfoo=bar")

    def test_blank_before_key_comment(self):
        with self.assertParseError("#2: blank line must precede key comment @"):
            ALACS().decode(b"//comment\n\nfoo=bar")

    def test_multiple_blank_lines(self):
        with self.assertParseError("#2: more than one blank line @/"):
            ALACS().decode(b"\n\nfoo=bar")

    def test_unclaimed_blank_line(self):
        with self.assertParseError("#3: unclaimed key comment or blank line @/foo"):
            ALACS().decode(b"foo=bar\n\n")

    def test_unclaimed_key_comment(self):
        with self.assertParseError("#2: unclaimed key comment or blank line @"):
            ALACS().decode(b"//comment")

    def test_missing_equals(self):
        with self.assertParseError("#1: malformed `key=value` association @"):
            ALACS().decode(b"foobar")

    def test_duplicate_key(self):
        with self.assertParseError("#3: duplicate key: foo @/foo"):
            ALACS().decode(b"foo=bar\nfoo=baz")


def problem_count() -> int:
    argv = ["alacs_test", "unit_tests"]  # argv[0] is (fictional) name of program
    result = unittest.main(module=alacs_test, argv=argv, exit=False).result
    return len(result.failures) + len(result.errors)
