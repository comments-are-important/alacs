/// <reference types="tree-sitter-cli/dsl" />
// @ts-check
export default grammar({

    name: "tindalwic", // text in nested dictionaries and lists with important comments

    rules: {

        // outermost context is a dictionary after an optional `#!`:
        file: $ => seq(optional($.shebang), optional($.prolog), repeat($.entry)),

        // all values have one of these three types (there's only one primitive type):
        text: $ => seq($._INDENT, optional($._text_block), $._DEDENT),
        dict: $ => seq($._INDENT, optional($.prolog), repeat($.entry), $._DEDENT),
        list: $ => seq($._INDENT, optional($.prolog), repeat($.item), $._DEDENT),

        // text is a contiguous block of equally indented lines:
        line: $ => /[^\n]*/,
        _text_block: $ => seq($._first_line, repeat($._another_line)),

        // comments are text except 1st line is before the block, flowing into it:
        _text_flow: $ => seq($.line, $._INDENT, repeat($._another_line), $._DEDENT),

        // comments are fully nodes in the parse and each has a topic it is about:
        shebang: $ => seq($._left_margin, '#!', $._text_flow), // file
        prolog: $ => seq($._left_margin, '#', $._text_flow),   // file dict list
        epilog: $ => seq($._left_margin, '#', $._text_flow),   // value
        comment: $ => seq($._left_margin, '//', $._text_flow), // key

        // compound types are arrays, each element has at least a value, possibly more:
        entry: $ => seq(optional($.gap), optional($.comment), $._key_value, optional($.epilog)),
        item: $ => seq(choice($._value, $._short_value), optional($.epilog)),
        _value: $ => choice(
            seq($._left_margin, '<>', $.text),
            seq($._left_margin, '{}', $.dict),
            seq($._left_margin, '[]', $.list),
        ),
        key: $ => $.text, // each dictionary entry requires a key (rule is only aliased)
        _key_value: $ => choice(
            seq($._left_margin, '@', alias($.text, $.key), $._value),
            seq($._left_margin, '<', alias($._TEXT_KEY, $.key), '>', $.text),
            seq($._left_margin, '{', alias($._DICT_KEY, $.key), '}', $.dict),
            seq($._left_margin, '[', alias($._LIST_KEY, $.key), ']', $.list),
            seq($._left_margin, alias($._SHORT_KEY, $.key), '=', alias($.short_line, $.text)),
        ),

        // there are shortcut one-line flavors for text values in both compound types:
        _short_value: $ => seq($._left_margin, alias($.short_text, $.text)),
        short_text: $ => alias($._SHORT_STR, $.line),
        short_line: $ => $.line,

        // some rules need to peek ahead a few chars
        gap: $ => seq($._PEEK_EMPTY, $._NEW_LINE),
        _left_margin: $ => seq($._PEEK_MARGIN, $._NEW_LINE, $._MARGIN),
        _first_line: $ => seq($._PEEK_MARGIN, /\n/, $._MARGIN, $.line),
        _another_line: $ => seq($._PEEK_MARGIN, '\n', $._MARGIN, $.line),
    },

    externals: $ => [
        // most tokens are mutually exclusive: grammar rules must
        // never ask for more than one from any single scanner call.
        $._NEW_LINE,    // LF or zero-width beginning of file
        $._MARGIN,      // the expected number of TABs starting at column 0
        $._SHORT_STR,   // empty or /[^#/@=<>{}\[\]\n\t][^\n]*/
        $._SHORT_KEY,   // empty or /[^#/@=<>{}\[\]\n\t][^=\n]*/ if peek('=')
        $._TEXT_KEY,    // rest of line if peek('>', EOF or LF)
        $._DICT_KEY,    // rest of line if peek('}', EOF or LF)
        $._LIST_KEY,    // rest of line if peek(']', EOF or LF)
        $._INDENT,      // ++margin zero-width
        // remaining tokens help the rules determine the structure: scanner
        // will be asked to select from among more than one of them.
        // until issue 5929 gets done all these must be zero-width
        $._DEDENT,      // --margin if EOF or peek(LF, not enough TABs)
        $._PEEK_EMPTY,  // if peek(NEW_LINE, EOF or LF)
        $._PEEK_MARGIN, // if peek(NEW_LINE, margin TABS)
    ],

    conflicts: $ => [[$.item], [$.entry]],

    extras: $ => [
        // empty to disable the builtin ignore whitespace stuff.
        // note "insert_final_newline = false" in `.editorconfig`: newlines here aren't
        // typical line termination chars. tindalwic does not use quotation for strings,
        // so a trailing (CR)LF at EOF can't be ignored. instead it uses things like
        // RegExp `/[^\n]*/` to finish lines without consuming any termination chars.
        // think of _NEW_LINE as: "nope, not done yet, here's another line to parse".
    ],

});
