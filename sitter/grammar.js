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
        _flow: $ => seq($.line, repeat(seq($._NEW_LINE, $._MARGIN, '\t', $.line))),
        text: $ => seq($._NEW_LINE, $._MARGIN, '\t', $._flow),

        shebang: $ => seq($._NEW_LINE, $._MARGIN, '#!', $._flow),
        prolog: $ => seq($._NEW_LINE, $._MARGIN, '#', $._flow),
        epilog: $ => seq($._NEW_LINE, $._MARGIN, '#', $._flow),
        key_comment: $ => seq($._NEW_LINE, $._MARGIN, '//', $._flow),

        item: $ => seq(
            $._NEW_LINE, $._MARGIN, $._value,
            optional($.epilog),
        ),
        _value: $ => choice(
            seq('<>', optional($.text)),
            seq('[]', optional($.list)),
            seq('{}', optional($.dict)),
            $.SHORT_ITEM,
        ),

        gap: $ => $._EMPTY_LINE,
        entry: $ => seq(
            optional($.gap),
            optional($.key_comment),
            $._NEW_LINE, $._MARGIN, $._key_value,
            optional($.epilog),
        ),
        _key_value: $ => choice(
            seq('@', $._flow, $._NEW_LINE, $._MARGIN, $._value),
            seq('<', $.TEXT_KEY, '>', optional($.text)),
            seq('[', $.LIST_KEY, ']', optional($.list)),
            seq('{', $.DICT_KEY, '}', optional($.dict)),
            seq($.SHORT_KEY, '=', $.line),
        ),

    },

    externals: $ => [
        $._NEW_LINE,
        $._MARGIN,
        $.INDENT,
        $.DEDENT,
        $._EMPTY_LINE,
        $.SHORT_ITEM,
        $.SHORT_KEY,
        $.TEXT_KEY,
        $.LIST_KEY,
        $.DICT_KEY,
        $.RECOVERY
    ],

    conflicts: $ => [[$._flow], [$.item], [$._value], [$.entry], [$._key_value]],

});
