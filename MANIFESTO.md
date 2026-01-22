# ALACS - Associative and Linear Arrays of Commented Strings

 + This is meant to be an informal description of the format.
 + See the [README](README.md) for links to other documentation.

A formal spec is tricky to write and would likely not be very helpful. More information
about that can be found in the non-normative [alacs.abnf](alacs.abnf) file.


## Line Oriented Pattern Matching

 + Based on these marker characters:
   + TAB **`#`** **`//`** **`<>`** **`[]`** **`{}`** **`=`**

ALACS reads data one line at a time, examining typically only a few bytes of it to
decide what to do next. Those decisions are final - they cannot be altered by any
subsequent line.


### Strict Encoding

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


### Indentation Demarks Nested Contexts

 + Similar to Python, YAML, Scala 3... except:
   + Tabs only, never spaces.
   + Strictly monotonically increasing.

If a line indicates the opening of a nested context, then all the lines within it will
immediately follow and will be indented by exactly one more tab than the opening line.
Every context is closed by EOF or by the next line with insufficient indentation.


## UTF-8 Contexts

 + This is the only primitive data type, there isn't even a null.
 + Any bytes following indentation are taken verbatim.
   + No nested context can be opened from within these contexts.
 + Used for both comments and string values.
   + Media type for comments: `text/markdown; charset=UTF-8; variant=GFM`

ALACS might be considered a lexer because it refrains from making many of the semantic
interpretations that a parser will. It doesn't even decode most of the UTF-8. Tools
like [Pydantic](https://pydantic.dev/) and [JSON Schema](https://json-schema.org/)
better address those concerns, and there is no reason to duplicate that functionality.

Comment text is [CommonMark](https://commonmark.org/) with the extensions allowed in
[GFM](https://github.github.com/gfm). It is suggested that applications adopt this same
spec for their string values, when possible. Their choices should be made explicit with
[contentMediaType](https://json-schema.org/understanding-json-schema/reference/non_json_data)
from JSON Schema.

Note that a line in this context might start with more tabs than just the monotonically
increasing rule dictates, and those in excess are part of the text.


### Comments: **`#`** _or (sometimes)_ **`//`**

 + Only allowed in specific locations - comments are not freely placed.
 + Marker must immediately follow indentation - no "end-of-line" comments.
 + Remainder of the opening line (even if empty) becomes the first line.
 + The **`//`** marker is used for keys in associative array contexts (see below).

Comments always have exactly one subject of discussion, but that is never another
comment (no meta comments). The allowed locations will be listed with each subject.

Note that the markers should only appear on the opening line, not repeated on every
line of the comment. The indentation is what determines the extent of the context.


### Strings: **`<>`**

 + The opening and closing angle brackets must be the first and last bytes on the line.
 + An optional **`#`** comment for the value can follow the context (not indented).
 + Empty and (most) single-line string values should use a special short syntax
   (described below, in the Linear Array and Associative Array sections).

An angle bracket context with one line that has only indentation is read as an empty
string value. So is an angle bracket context with zero lines. The decoding is lenient,
But during encoding the special short syntax (see below) is always used.

Similarly, an angle bracket context with one non-empty line is read as a single-line
string value. Many (most) such values will be encoded using the special short syntax,
but some (see below) must use the longer angle bracket syntax to avoid confusion.


## Array Contexts

 + Marked similar to strings, but using square and curly (instead of angle) brackets.
 + Can have two **`#`** comments (both optional) about the array itself:
   + An introduction at the very top, indented.
   + Following (like string value comments) the array context (not indented).
     + There is an exception to this rule for the outermost context (see below).

Unlike strings, a context of zero lines is unambiguous, representing an empty array
with no introductory comment.


### Linear Array: **`[]`**

 + Each line inside the context contributes to a value that is appended in order.
 + A line that starts (after indentation) with an opening bracket marker:
   + Must immediately end with the corresponding closing bracket (only two bytes long).
   + Opens a nested context of the type indicated by the bracket.
 + A line that does not start with an opening bracket is a single-line string value.
   + Can have an optional following **`#`** comment.

If a single-line string value starts with any any of the pattern matching marker chars
then it will be encoded with the longer angle bracket syntax (thus taking two lines).
This rule is intentionally stringent. Relaxing it would not necessarily cause parsing
problems, but would really hamper the ability to quickly scan down the indented side to
get a rough overview of the data.

The amount of vertical space required for lists of short values is likely to be a
common complaint, but supporting inline lists makes the syntax rules significantly more
complicated. The workaround for this scenario is to store a string value and split it
as needed in the application code.


### Associative Array: **`{}`** _with_ **`=`** _and_ **`//`**

 + A line that starts (after indentation) with an opening bracket marker:
   + Must end with the corresponding closing bracket, enclosing a key.
 + Keys are decoded to strings, and duplicates are illegal.
   + Each key can have an optional **`//`** comment that immediately precedes it...
   + And/or one optional blank line (preceding the comment, if present).
 + A line that does not start with a bracket marker must contain an **`=`** marker.
   + The key precedes the first **`=`**, the single-line string value follows it.
   + The string value can have an optional following **`#`** comment.

If a key starts with any of the pattern matching marker chars, or if **`=`** appears
anywhere in the key, or if the string value is more than one line, then the special
short syntax may not be used.

There is no way to embed a newline into a key. The workaround is to mimic `JQ`'s
[entries](https://jqlang.org/manual/#to_entries-from_entries-with_entries) operators.


## Outermost Context is _almost_ an Implicit Associative Array

 + Can have an additional optional **`#!`** "hashbang" comment starting on first line.
 + An optional introductory comment is allowed, following the hashbang if present.
 + However: no following comment is allowed.

This choice is inspired by TOML - the flexibility of JSON and YAML in this regard comes
with little benefit and significant costs. The very common workaround of using a single
generic `data` or `results` key, or, better, an appropriately named specific key, is
easier when paired with Pydantic or other tools that impose schemas on the content.
