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
        dict: $ => seq($._INDENT, optional($.prolog), repeat($.entry), $._DEDENT),
        list: $ => seq($._INDENT, optional($.prolog), repeat($.item), $._DEDENT),
        text: $ => seq($._INDENT, $._first, repeat(seq($._CONTINUE, $._more)), $._DEDENT),
        _spill: $ => seq($._INDENT, $._more, repeat(seq($._CONTINUE, $._more)), $._DEDENT),

        line: $ => /[^\n]*/,
        _first: $ => seq(/\n/, $._MARGIN, $.line), // RegExp is invisible to query,
        _more: $ => seq('\n', $._MARGIN, $.line), // ... but literals can be injected
        _flow: $ => seq($.line, optional($._spill)),

		gap: $ => seq($._FALSY, $._NEW_LINE),
        shebang: $ => seq($._TRUTHY, $._NEW_LINE, $._MARGIN, '#!', $._flow),
        prolog: $ => seq($._TRUTHY, $._NEW_LINE, $._MARGIN, '#', $._flow),
        epilog: $ => seq($._TRUTHY, $._NEW_LINE, $._MARGIN, '#', $._flow),
        key_comment: $ => seq($._TRUTHY, $._NEW_LINE, $._MARGIN, '//', $._flow),

        item: $ => seq(
            $._TRUTHY, $._NEW_LINE, $._MARGIN, $._value,
            optional($.epilog),
        ),
        _value: $ => choice(
            seq('<>', optional($.text)),
            seq('[]', optional($.list)),
            seq('{}', optional($.dict)),
            $.SHORT_ITEM,
        ),

        entry: $ => seq(
            optional($.gap),
            optional($.key_comment),
            $._TRUTHY, $._NEW_LINE, $._MARGIN, $._key_value,
            optional($.epilog),
        ),
        LONG_KEY: $ => $._flow,
        _key_value: $ => choice(
            seq('@', $.LONG_KEY, /\n/, $._MARGIN, $._value),
            seq('<', $.TEXT_KEY, '>', optional($.text)),
            seq('[', $.LIST_KEY, ']', optional($.list)),
            seq('{', $.DICT_KEY, '}', optional($.dict)),
            seq($.SHORT_KEY, '=', $.line),
        ),

    },

    externals: $ => [
        // first group of tokens are mutually exclusive. grammar rules must never allow
        // more than one into `valid_symbols` for any single scanner call.
        $._NEW_LINE,  // LF or zero-width beginning of file
        $._MARGIN,    // the expected number of TAB chars starting at column 0
        $.SHORT_ITEM, // empty or /[^[:reserved_char:]][^\n]*/
        $.SHORT_KEY,  // empty or /[^[:reserved_char:]][^=\n]*/ if peek: '='
        $.TEXT_KEY,   // rest of line if peek: '>' + (EOF|LF)
        $.LIST_KEY,   // rest of line if peek: ']' + (EOF|LF)
        $.DICT_KEY,   // rest of line if peek: '}' + (EOF|LF)
        // sentinel marks end of exclusive group, must not be used in any rule
        $.RECOVERY,   // indicates error condition call
        // remaining tokens help the rules determine the structure so scanner will be
        // asked to select from among them (sometimes one but often multiple).
        $._TRUTHY,    // zero-width if peek: NEW_LINE+!LF
        $._FALSY,     // zero-width if peek: NEW_LINE+LF
        $._INDENT,     // zero-width ++margin if peek: LF + more TABs than expected
        $._DEDENT,     // zero-width --margin if EOF or peek: LF + insufficient TABs
        $._CONTINUE,   // zero-width no-op if peek: LF + margin TABs (or more)
    ],

    conflicts: $ => [[$.item], [$.entry]],

});
