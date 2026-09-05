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
        // think of NEW_LINE as: "nope, not done yet, here's another line to parse".
    ],

    rules: {

        file: $ => seq(optional($.shebang), optional($.prolog), repeat($.entry)),
        dict: $ => seq($.INDENT, optional($.prolog), repeat($.entry), $.DEDENT),
        list: $ => seq($.INDENT, optional($.prolog), repeat($.item), $.DEDENT),

        line: $ => /[^\n]*/,
        flow: $ => seq($.line, repeat(seq($.NEW_LINE, $.MARGIN, '\t', $.line))),
        text: $ => seq($.NEW_LINE, $.MARGIN, '\t', $.flow),

        shebang: $ => seq('#!', $.flow),
        prolog: $ => seq($.NEW_LINE, $.MARGIN, '#', $.flow),
        epilog: $ => seq($.NEW_LINE, $.MARGIN, '#', $.flow),
        key_comment: $ => seq($.NEW_LINE, $.MARGIN, '//', $.flow),

        item: $ => seq(
            $.NEW_LINE, $.MARGIN, $._value,
            optional($.epilog),
        ),
        _value: $ => choice(
            seq('<>', optional($.text)),
            seq('[]', optional($.list)),
            seq('{}', optional($.dict)),
            $.SHORT_ITEM,
        ),

        gap: $ => $.EMPTY_LINE,
        entry: $ => seq(
            optional($.gap),
            optional($.key_comment),
            $.NEW_LINE, $.MARGIN, $._key_value,
            optional($.epilog),
        ),
        _key_value: $ => choice(
            seq('@', $.flow, $.NEW_LINE, $.MARGIN, $._value),
            seq('<', $.TEXT_KEY, '>', optional($.text)),
            seq('[', $.LIST_KEY, ']', optional($.list)),
            seq('{', $.DICT_KEY, '}', optional($.dict)),
            seq($.SHORT_KEY, '=', $.line),
        ),

    },

    externals: $ => [
        // first 5 tokens are about structure and may be `valid_symbols` in any call...
        $.NEW_LINE,   // LF or zero-width beginning of file
        $.MARGIN,     // the expected number of TAB chars starting at column 0
        $.INDENT,     // zero-width ++margin if peek: LF + more TABs than expected
        $.DEDENT,     // zero-width --margin if EOF or peek: LF + insufficient TABs
        $.EMPTY_LINE, // NEW_LINE with peek: LF (but not EOF)
        // these 5 tokens are mutually exclusive with each other (but not those above)...
        $.SHORT_ITEM, // empty or /[^[:reserved_char:]][^\n]*/
        $.SHORT_KEY,  // empty or /[^[:reserved_char:]][^=\n]*/
        $.TEXT_KEY,   // $.line if peek: '>' + (EOF|LF)
        $.LIST_KEY,   // $.line if peek: ']' + (EOF|LF)
        $.DICT_KEY,   // $.line if peek: '}' + (EOF|LF)
        // the last token must not be used by any rules in the grammar...
        $.RECOVERY    // sentinel indicating error recovery
    ],

    conflicts: $ => [[$.flow], [$.item], [$._value], [$.entry], [$._key_value]],

});
