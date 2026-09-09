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
        text: $ => seq($._INDENT, optional($._string), $._DEDENT),
        _flow: $ => seq($._INDENT, repeat($._another_line), $._DEDENT),

        line: $ => /[^\n]*/,
        _another_line: $ => seq($._CONTINUE, '\n', $._MARGIN, $.line),
        _string: $ => seq($._CONTINUE, /\n/, $._MARGIN, $.line, repeat($._another_line)),

        prolog: $ => seq($._PEEK_SOME, $._NEW_LINE, $._MARGIN, '#', $.line, optional($._flow)),
        epilog: $ => seq($._PEEK_SOME, $._NEW_LINE, $._MARGIN, '#', $.line, optional($._flow)),
        comment: $ => seq($._PEEK_SOME, $._NEW_LINE, $._MARGIN, '//', $.line, optional($._flow)),
        shebang: $ => seq($._PEEK_SOME, $._NEW_LINE, $._MARGIN, '#!', $.interpreter, optional($._flow)),
        interpreter: $ => /[^\n]+/,

        item: $ => seq(
            $._PEEK_SOME, $._NEW_LINE, $._MARGIN, choice($._value, $._short_text),
            optional($.epilog),
        ),
        short_line: $ => alias($.SHORT_STR, $.line),
        _short_text: $ => alias($.short_line, $.text),
        _value: $ => choice(
            seq('<>', $.text),
            seq('[]', $.list),
            seq('{}', $.dict),
            // can't put short item here (not allowed after '@')
        ),

        entry: $ => seq(
            optional($.gap),
            optional($.comment),
            $._PEEK_SOME, $._NEW_LINE, $._MARGIN, $._key_value,
            optional($.epilog),
        ),
        gap: $ => seq($._PEEK_EMPTY, $._NEW_LINE),
        key: $ => seq($.line, optional($._flow)),
        short_value: $ => $.line,
        _key_value: $ => choice(
            seq('@', $.key, /\n/, $._MARGIN, $._value),
            seq('<', alias($.TEXT_KEY, $.key), '>', $.text),
            seq('[', alias($.LIST_KEY, $.key), ']', $.list),
            seq('{', alias($.DICT_KEY, $.key), '}', $.dict),
            seq(alias($.SHORT_KEY, $.key), '=', alias($.short_value, $.text)),
        ),

    },

    externals: $ => [
        // first group of tokens are mutually exclusive. grammar rules must never allow
        // more than one into `valid_symbols` for any single scanner call.
        $._NEW_LINE,   // LF or zero-width beginning of file
        $._MARGIN,     // the expected number of TABs starting at column 0
        $._INDENT,     // ++margin (unconditionally - rules are in charge)
        $.SHORT_STR,  // empty or /[^[:reserved_char:]][^\n]*/
        $.SHORT_KEY,   // empty or /[^[:reserved_char:]][^=\n]*/ if peek('=')
        $.TEXT_KEY,    // rest of line if peek('>', EOF or LF)
        $.LIST_KEY,    // rest of line if peek(']', EOF or LF)
        $.DICT_KEY,    // rest of line if peek('}', EOF or LF)
        // sentinel marks end of exclusive group, must not be used in any rule
        $.RECOVERY,    // indicates error condition call
        // remaining tokens help the rules determine the structure so scanner will be
        // asked to select from among them (sometimes one but often multiple).
        // until issue 5929 gets done all these must be zero-width
        $._PEEK_EMPTY, // if peek(NEW_LINE, EOF or LF)
        $._PEEK_SOME,  // if peek(NEW_LINE, !(EOF or LF))
        $._DEDENT,     // --margin if EOF or peek(LF, less than margin TABs)
        $._CONTINUE,   // if peek(LF, margin TABs or more)
    ],

    conflicts: $ => [[$.item], [$.entry]],

});
