# ALACS - Associative and Linear Arrays of Commented Strings

 + This is meant to be an informal almost-but-not-quite-a spec.
 + See the [README](README.md) for links to other documentation.

A formal spec is tricky to write and would likely not be very helpful. More details
about that can be found in the non-normative [alacs.abnf](alacs.abnf) file.


## Strict Encoding

```ini
[*.alacs]
charset = utf-8
end_of_line = lf
indent_style = tab
insert_final_newline = false
max_line_length = off
trim_trailing_whitespace = false
```

ALACS data is required to conform to these [EditorConfig](https://editorconfig.org/)
settings. Other formats accommodate various encodings and use of whitespace, but that
flexibility comes at a cost - sometimes subtle, like the impact on content-addressable
storage. The limitations of tools on different platforms in the past made it arguably
worth the price, but that is not the case today.


## Indentation Demarks Nested Contexts

 + Similar to Python, YAML, Scala 3... except:
   + Tab chars **only**, never spaces.
   + Strictly monotonically increasing indentation.

If a line indicates the opening of a nested context, then all the lines within it will
immediately follow and will be indented by **exactly one more tab char** than the
opening line. Every context is closed by EOF or by the next line with insufficient
indentation - unlike TOML, where lines within a single context can be non-contiguous.


## Line Oriented Pattern Matching

 + In precedence order:
   + At end: **`|`**, **`>`**, **`:`**, **`[]`**
   + At beginning (after indentation): **`#`**
   + Inside (first occurrence): **`=`**

ALACS reads data one line at a time, examining typically only a few bytes of it to
decide what to do next. Those decisions are final - they cannot be altered by any
subsequent line. The UTF-8 need not be fully decoded at this stage.

The patterns are context sensitive: some are only considered in certain locations. For
example, the **`=`** pattern is used in associative array contexts. The pattern markers
don't always stand out on their own. The precedence rules are very simple for computers
to follow, but can be a bit tricky for humans. In the past this would likely have been
an unsurmountable problem, but the wide support for syntax highlighing changes things.


## Comments: **`#`**

 + Only recognized in specific locations - comments are not freely placed.
 + Remainder of the opening line (even if empty) becomes the first line.
 + Each subsequent line in the context (stripped of indentation) adds one more line.
 + No nested context can be opened from inside a comment.

Comments always have exactly one subject of discussion, but that is never another
comment (no meta allowed). The allowed locations will be listed with each subject.

The text inside comments is (CommonMark)[https://commonmark.org/]. Extensions that are
exactly the same in both GitHub and GitLab flavors may be used. ALACS itself does not
parse or even decode this text, it is just verbatim UTF-8 - but software that reads
this data can know how to treat it.

Note that the **`#`** marker should only appear on the opening line, not repeated on
every line of the comment. The indentation is what determines the extent of the
context, and syntax highlighting should make this apparent.


## Strings: **`|`** _or_ **`>`**

 + No other primitive types, no quotation/escaping mechanism.
 + A **`>`** indicates CommonMark (as with comments).
 + Marker is preceded by key if inside an associative array context.
   + A single-line syntax for this using **`=`** will be discussed later.
 + Each subsequent line in the context (stripped of indentation) adds one more line.
 + No nested context can be opened from inside a string value.
 + An optional comment for the value can follow it.

Formats like YAML and TOML acknowledge the burden of quotes in JSON, allowing them to
be omitted in special cases. ALACS takes that idea to the extreme, requiring no quotes
at all. One consequence there is no way to support any of the non-string types that
those other formats do. Something like [Pydantic](https://pydantic.dev/) can be used to
validate and convert the strings to appropriate types. There is no reason to duplicate
that functionality here.

ALACS takes inspiration for these marker chars from YAML, but goes a little bit further
by delegating to CommonMark.

A comment for a string value always immediately follows and closes the text context -
the two opening lines will line up vertically, and any indented text lines will line up
at one tab stop more.


## Linear Array: **`[]`**

 + Marker is preceded by key if nested inside an associative array context.
 + Each line of the context adds one value (with its trailing comment) to the array.
   + If a line has no marker at either end it is a single-line string value.
   + Nulls are not supported (use empty string values).
 + Can have two comments (both optional) about the array itself:
   + An introduction at the very top, indented.
   + Following (and closing, like string value comments) the array context.

The amount of vertical space required for lists of short values is likely to be a
common complaint, but supporting inline lists makes the syntax rules significantly more
complicated. A workaround for this scenario is to store a string value and split it as
needed at a higher level.


## Associative Array: **`:`** _with_ **`=`**

 + Marker is preceded by key if nested inside another associative array context.
 + Each line of the context adds one association to the array, and starts with the key.
   + Keys are decoded to strings, order is maintained, and duplicates are illegal.
   + A single-line string value can be on the same line as the key following: **`=`**
   + All values can have their usual optional trailing comments.
   + Each key can have an optional comment that immediately precedes it,
     and/or one optional blank line preceding the comment (if present).
 + Can have two comments (both optional) about the array itself:
   + An introduction at the very top, indented.
   + Following (and closing, like string value comments) the array context.


## File Context

 + Almost same as associative array context, except:
   + Optionally an additional **#!** hashbang comment on first line.
   + The optional final trailing comment for the file array is at zero indent.

This choice is inspired by TOML - the flexibility of JSON and YAML in this regard comes
with little benefit and significant costs. The very common workaround of using a single
generic `data` or `results` key, or, better, an appropriately named specific key, is
easier when paired with Pydantic or other tools that impose schemas on the content.
