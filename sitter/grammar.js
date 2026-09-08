/// <reference types="tree-sitter-cli/dsl" />
// @ts-check
export default grammar({

    name: "tindalwic",

    extras: $ => [
        // empty to disable the builtin ignore whitespace stuff.
        // note "insert_final_newline = false" in `.editorconfig`: newlines here aren't
        // typical line termination chars. tindalwic does not use quotation for strings,
        // so a trailing (CR)LF at EOF can't be ignored. instead it uses things like
        // RegExp `/[^\n]*/` to finish lines without consuming any termination chars.
        // think of _NEW_LINE as: "nope, not done yet, here's another line to parse".
    ],

    rules: {

        file: $ => seq(optional($.shebang), optional($.prolog), repeat($.entry)),

        dict: $ => choice($._ELIDED, $._entries),
        list: $ => choice($._ELIDED, $._items),
        text: $ => choice($._ELIDED, $._lines),

        _entries: $ => seq($._INDENT, optional($.prolog), repeat($.entry), $._DEDENT),
        _items: $ => seq($._INDENT, optional($.prolog), repeat($.item), $._DEDENT),
        _lines: $ => seq($._INDENT, $._first, repeat(seq($._CONTINUE, $._more)), $._DEDENT),
        _spill: $ => seq($._INDENT, $._more, repeat(seq($._CONTINUE, $._more)), $._DEDENT),

        line: $ => /[^\n]*/,
        _first: $ => seq(/\n/, $._MARGIN, $.line), // RegExp is invisible to query,
        _more: $ => seq('\n', $._MARGIN, $.line), // ... but literals can be injected
        _flow: $ => seq($.line, optional($._spill)),

        gap: $ => seq($._EMPTY_LINE, $._NEW_LINE),
        prolog: $ => seq($._SOME_LINE, $._NEW_LINE, $._MARGIN, '#', $._flow),
        epilog: $ => seq($._SOME_LINE, $._NEW_LINE, $._MARGIN, '#', $._flow),
        comment: $ => seq($._SOME_LINE, $._NEW_LINE, $._MARGIN, '//', $._flow),
        interpreter: $ => /[^\n]+/,
        shebang: $ => seq($._SOME_LINE, $._NEW_LINE, $._MARGIN, '#!', $.interpreter, optional($._spill)),

        item: $ => seq(
            $._SOME_LINE, $._NEW_LINE, $._MARGIN, choice($._value, alias($.SHORT_ITEM, $.text)),
            optional($.epilog),
        ),
        _value: $ => choice(
            seq('<>', $.text),
            seq('[]', $.list),
            seq('{}', $.dict),
        ),

        entry: $ => seq(
            optional($.gap),
            optional($.comment),
            $._SOME_LINE, $._NEW_LINE, $._MARGIN, $._key_value,
            optional($.epilog),
        ),
        key: $ => $._flow,
        SHORT_VALUE: $ => $.line,
        _key_value: $ => choice(
            seq('@', $.key, /\n/, $._MARGIN, $._value),
            seq('<', alias($.TEXT_KEY, $.key), '>', $.text),
            seq('[', alias($.LIST_KEY, $.key), ']', $.list),
            seq('{', alias($.DICT_KEY, $.key), '}', $.dict),
            seq(alias($.SHORT_KEY, $.key), '=', alias($.SHORT_VALUE, $.text)),
        ),

    },

    externals: $ => [
        // first group of tokens are mutually exclusive. grammar rules must never allow
        // more than one into `valid_symbols` for any single scanner call.
        $._NEW_LINE,   // LF or zero-width beginning of file
        $._MARGIN,     // the expected number of TABs starting at column 0
        $.SHORT_ITEM,  // empty or /[^[:reserved_char:]][^\n]*/
        $.SHORT_KEY,   // empty or /[^[:reserved_char:]][^=\n]*/ if peek('=')
        $.TEXT_KEY,    // rest of line if peek('>', EOF or LF)
        $.LIST_KEY,    // rest of line if peek(']', EOF or LF)
        $.DICT_KEY,    // rest of line if peek('}', EOF or LF)
        // sentinel marks end of exclusive group, must not be used in any rule
        $.RECOVERY,    // indicates error condition call
        // remaining tokens help the rules determine the structure so scanner will be
        // asked to select from among them (sometimes one but often multiple).
        // until issue 5929 gets done all these must be zero-width
        $._EMPTY_LINE, // if peek(NEW_LINE, EOF or LF)
        $._SOME_LINE,  // if peek(NEW_LINE, !(EOF or LF))
        $._INDENT,     // ++margin if peek(LF, more TABs than expected)
        $._DEDENT,     // --margin if EOF or peek(LF, insufficient TABs)
        $._CONTINUE,   // if peek(LF, margin TABs or more)
		$._ELIDED,     // if valid[INDENT] and peek(LF, margin TABs exactly)
    ],

    conflicts: $ => [[$.item], [$.entry]],

});
