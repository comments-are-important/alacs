from typing import Any, TypeVar, NamedTuple

from deepdiff import DeepDiff
from ruamel.yaml.comments import CommentedMap, CommentedSeq, Comment as CommentObject
from ruamel.yaml.tokens import CommentToken
from ruamel.yaml.scalarstring import ScalarString

from . import FileSeparated

T = TypeVar("T")


class Translated(NamedTuple):
    data: dict
    comments: list[str]


def _extract_ruamel_comments(any: Any, tokens: list[CommentToken]) -> None:
    match any:
        case None | str():
            pass
        case CommentToken():
            tokens.append(any)
        case CommentObject():
            _extract_ruamel_comments(any.pre, tokens)
            _extract_ruamel_comments(any.comment, tokens)
            _extract_ruamel_comments(any.end, tokens)
            _extract_ruamel_comments(any.items, tokens)
        case list():
            for value in any:
                _extract_ruamel_comments(value, tokens)
        case dict():
            for value in any.values():
                _extract_ruamel_comments(value, tokens)
        case _:
            raise ValueError(f"unexpected type: {type(any)}")


def _separate_ruamel_value(any: Any, tokens: list[CommentToken]) -> Any:
    match any:
        case CommentedSeq():
            _extract_ruamel_comments(any.ca, tokens)
            return [_separate_ruamel_value(it, tokens) for it in any]
        case CommentedMap():
            _extract_ruamel_comments(any.ca, tokens)
            return {k: _separate_ruamel_value(v, tokens) for k, v in any.items()}
        case ScalarString():
            return str(any)
        case _:
            raise ValueError(f"unexpected type: {type(any)}")


def extract_ruamel_comments(file: CommentedMap) -> Translated:
    comments = list[CommentToken]()
    data = _separate_ruamel_value(file, comments)
    assert isinstance(data, dict)
    comments.sort(key=lambda it: it.start_mark.line)
    index = len(comments) - 1
    while index > 0:
        if comments[index] is comments[index - 1]:
            # not sure why duplicates are stored, but it seems to be intentional.
            # detecting and correcting the situation is super easy and 100% safe...
            del comments[index]
        index -= 1
    lines = list[str]()
    for comment in comments:
        for line in comment.value.splitlines():
            line = line.lstrip()
            if line:
                lines.append(line)
    return Translated(data, lines)


def diff_any(was: T, now: T) -> bool:
    if was == now:
        return False
    print()
    print(DeepDiff(was, now, verbose_level=2).pretty())
    return True


def diff_ruamel(was: CommentedMap, now: CommentedMap) -> bool:
    return diff_any(extract_ruamel_comments(was), extract_ruamel_comments(now))


def diff_translate(was: FileSeparated, now: CommentedMap) -> bool:
    extracted = extract_ruamel_comments(now)
    return diff_any(Translated(was.python, was.comments), extracted)
    #return diff_any(was.python, extracted.data)
