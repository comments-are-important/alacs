import re
from collections import UserString
from unittest import TestCase, main
import alacs_test
from alacs import Memory, UTF8, Comment, Text, Key, Indent, File, List

# focus is on filling in gaps left  by the timing script in alacs_test.__main__
# goal is to test all error branches to get 100% coverage of alacs.__init__


class TestUTF8(TestCase):
    def test_repr(self):
        self.assertEqual(repr(UTF8()), "<UTF8=>")
        self.assertEqual(repr(Comment(UserString("c"))), "<Comment=c>")
        self.assertEqual(repr(Text("1", "2")), "<Text=1\n2>")

    def test_normalize(self):
        text = Text(b"1\n2\n3", bytearray(b"4\n5\n6"), memoryview(b"7\n8\n9"))
        text.normalize(None)
        self.assertEqual(len(text), 9)


class TestKey(TestCase):
    def test_illegal(self):
        literal = "newline in key"
        pattern = re.compile(f"\\A{re.escape(literal)}\\z")
        maximum = 10
        for index in range(maximum + 1):
            illegal = f"{'x' * index}\n{'x' * (maximum - index)}"
            self.assertRaisesRegex(ValueError, pattern, Key, illegal)


class TestIndent(TestCase):
    def test_illegal(self):
        literal = "indent must be tab chars only"
        pattern = re.compile(f"\\A{re.escape(literal)}\\z")
        self.assertRaisesRegex(AssertionError, pattern, Indent, b" ")

    def test_negative(self):
        literal = "indent can't go negative"
        pattern = re.compile(f"\\A{re.escape(literal)}\\z")
        self.assertRaisesRegex(AssertionError, pattern, Indent(b"").less)

    def test_zero(self):
        indents = list[Indent]()
        indents.append(Indent(b""))
        indents.append(indents[-1].more())
        indents.append(indents[-1].more())
        indents.append(indents[-1].more())
        for index, indent in enumerate(indents):
            indent._key = str(index)
        self.assertEqual(repr(indents[-1]), "<Indent#3@0.1.2.3>")
        self.assertIs(indents[0], indents[2].zero())
        for index in range(len(indents)):
            self.assertIsNone(indents[index]._key)


class TestErrors(TestCase):
    def test_empty(self):
        message = "one two five"
        self.assertIs(Memory()._error(message), message)


class TestPython(TestCase):
    def test_impossible_none_no_error(self):
        class Impossible(Memory):
            def _python(self, any):
                # actual code never returns None without also adding an error
                return None

        literal = "impossible: got None, but no error"
        pattern = re.compile(f"\\A{re.escape(literal)}\\z")
        self.assertRaisesRegex(AssertionError, pattern, Impossible().python, File())

    def test_impossible_type(self):
        class Impossible(Memory):
            def _python(self, any):
                # actual code always returns dict for a File
                return ...

        literal = "impossible: got <class 'ellipsis'>"
        pattern = re.compile(f"\\A{re.escape(literal)}\\z")
        self.assertRaisesRegex(AssertionError, pattern, Impossible().python, File())

    def illegal(self, message: str) -> str:
        return "illegal non-`Value` data:\n\t" + message

    def test_illegal_key(self):
        literal = self.illegal("@[Ellipsis]: key is <class 'ellipsis'>")
        pattern = re.compile(f"\\A{re.escape(literal)}\\z")
        file = File()
        file[...] = ...  # type: ignore
        self.assertRaisesRegex(ValueError, pattern, Memory().python, file)

    def test_illegal_value(self):
        literal = self.illegal("@.x: value is <class 'ellipsis'>")
        pattern = re.compile(f"\\A{re.escape(literal)}\\z")
        file = File(x=...)  # type: ignore
        self.assertRaisesRegex(ValueError, pattern, Memory().python, file)


class TestFile(TestCase):
    def test_impossible_none_no_error(self):
        class Impossible(Memory):
            def _value(self, any):
                # actual code never returns None without also adding an error
                return None

        literal = "impossible: got None, but no error"
        pattern = re.compile(f"\\A{re.escape(literal)}\\z")
        self.assertRaisesRegex(AssertionError, pattern, Impossible().file, {})

    def test_impossible_type(self):
        class Impossible(Memory):
            def _value(self, any):
                # actual code always returns File for a Mapping
                return ...

        literal = "impossible: got <class 'ellipsis'>"
        pattern = re.compile(f"\\A{re.escape(literal)}\\z")
        self.assertRaisesRegex(AssertionError, pattern, Impossible().file, {})

    def test_none_is_empty_text(self):
        self.assertEqual(File(k=Text()), Memory().file({"k": None}))

    def illegal(self, message: str) -> str:
        return "can't be converted to `Value`:\n\t" + message

    def test_illegal_key(self):
        literal = self.illegal("@[Ellipsis]: key is <class 'ellipsis'>")
        pattern = re.compile(f"\\A{re.escape(literal)}\\z")
        self.assertRaisesRegex(ValueError, pattern, Memory().file, {...: None})

    def test_illegal_value(self):
        literal = self.illegal("@.k: value is <class 'ellipsis'>")
        pattern = re.compile(f"\\A{re.escape(literal)}\\z")
        self.assertRaisesRegex(ValueError, pattern, Memory().file, {"k": ...})

    def test_illegal_list_item(self):
        literal = self.illegal("@.k[0]: value is <class 'ellipsis'>")
        pattern = re.compile(f"\\A{re.escape(literal)}\\z")
        self.assertRaisesRegex(ValueError, pattern, Memory().file, {"k": [...]})

class TestEncode(TestCase):
    def test_denormalized(self):
        text = Text("")
        text.comment_after = Comment()
        text.comment_after.append(b"") # now it is not normalized
        with Memory().encode(File(k=text)) as buffer:
            alacs = buffer.tobytes().decode()
            self.assertEqual(alacs,"k=\n#")
    def illegal(self, message: str) -> str:
        return "illegal non-`Value` data:\n\t" + message

    def test_illegal_key(self):
        literal = self.illegal("@Ellipsis: key is <class 'ellipsis'>")
        pattern = re.compile(f"\\A{re.escape(literal)}\\z")
        alacs = File()
        alacs[...]=... # type: ignore
        self.assertRaisesRegex(ValueError, pattern, Memory().encode, alacs)

    def test_illegal_value(self):
        literal = self.illegal("#1: @k: value is <class 'ellipsis'>")
        pattern = re.compile(f"\\A{re.escape(literal)}\\z")
        alacs = File(k=...) # type: ignore
        self.assertRaisesRegex(ValueError, pattern, Memory().encode, alacs)

    def test_illegal_list_item(self):
        literal = self.illegal("#2: @k[0]: value is <class 'ellipsis'>")
        pattern = re.compile(f"\\A{re.escape(literal)}\\z")
        alacs = File(k=List(...)) # type: ignore
        self.assertRaisesRegex(ValueError, pattern, Memory().encode, alacs)


class TestDecodeErrors(TestCase):
    """Tests for invalid input handling in Memory.decode()"""

    def assertDecodeError(self, data: bytes, *substrings: str) -> None:
        """Helper to check that decode raises ValueError containing all substrings."""
        with self.assertRaises(ValueError) as ctx:
            Memory().decode(data)
        message = str(ctx.exception)
        for substring in substrings:
            self.assertIn(substring, message)

    # ---- indentation errors ----

    def test_excess_indentation_single_line(self):
        self.assertDecodeError(b"\t\tfoo=bar", "excess indentation")

    def test_excess_indentation_multiple_lines(self):
        self.assertDecodeError(
            b"\t\tfoo=bar\n\t\tbaz=qux",
            "(2 lines)",
            "indentation",
        )

    # ---- malformed openings ----

    def test_malformed_text_opening_in_dict(self):
        self.assertDecodeError(b"<foo", "malformed text opening")

    def test_malformed_text_opening_in_list(self):
        self.assertDecodeError(b"[key]\n\t<foo", "malformed text opening")

    def test_malformed_list_opening_in_dict(self):
        self.assertDecodeError(b"[foo", "malformed linear array opening")

    def test_malformed_list_opening_in_list(self):
        self.assertDecodeError(b"[key]\n\t[foo", "malformed linear array opening")

    def test_malformed_dict_opening_in_dict(self):
        self.assertDecodeError(b"{foo", "malformed associative array opening")

    def test_malformed_dict_opening_in_list(self):
        self.assertDecodeError(b"[key]\n\t{foo", "malformed associative array opening")

    # ---- comment errors ----

    def test_unattached_comment_in_list(self):
        # Comment after a list item, then another comment with no item to attach to
        self.assertDecodeError(
            b"[key]\n\tvalue\n\t#attached\n\t#unattached", "unattached comment"
        )

    def test_key_comment_in_list_context(self):
        self.assertDecodeError(b"[key]\n\t//comment", "key comment in list context")

    def test_illegal_comment_position_in_dict(self):
        # A # comment after a value's comment_after, with no next entry to attach to
        self.assertDecodeError(
            b"foo=bar\n#attached\n#illegal", "illegal position for comment"
        )

    def test_malformed_key_comment(self):
        # Single / instead of //
        self.assertDecodeError(b"/comment", "malformed key comment")

    def test_multiple_key_comments(self):
        self.assertDecodeError(
            b"//comment1\n//comment2\nfoo=bar",
            "more than one key comment",
        )

    # ---- blank line errors ----

    def test_blank_before_key_comment(self):
        self.assertDecodeError(
            b"//comment\n\nfoo=bar",
            "blank line must precede key comment",
        )

    def test_multiple_blank_lines(self):
        self.assertDecodeError(b"\n\nfoo=bar", "more than one blank line")

    def test_unclaimed_blank_line(self):
        # Blank line at end with no following key (needs explicit blank, not just trailing newline)
        self.assertDecodeError(b"foo=bar\n\n", "unclaimed key comment or blank line")

    def test_unclaimed_key_comment(self):
        # Key comment at end with no following key
        self.assertDecodeError(b"//comment", "unclaimed key comment or blank line")

    # ---- key errors ----

    def test_missing_equals(self):
        self.assertDecodeError(b"foobar", "malformed `key=value` association")

    def test_duplicate_key(self):
        self.assertDecodeError(b"foo=bar\nfoo=baz", "duplicate key")


def run_all_tests_return_problem_count() -> int:
    argv = ["alacs_test", "unit_tests"]  # argv[0] is (fictional) name of program
    result = main(module=alacs_test, argv=argv, exit=False).result
    return len(result.failures) + len(result.errors)
