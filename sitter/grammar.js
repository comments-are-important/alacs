/// <reference types="tree-sitter-cli/dsl" />
// @ts-check
export default grammar({

    name: "tindalwic",

    extras: $ => [
        // empty to disable the builtin ignore whitespace stuff
    ],

    externals: $ => [
        $.NEWLINE, // either EOF or a LF char
        // these three symbols are only recognized if column > 0:
        $._ANGLE,   // a key with lookahead: '>' $.NEWLINE
        $._SQUARE,  // a key with lookahead: ']' $.NEWLINE
        $._CURLY,   // a key with lookahead: '}' $.NEWLINE
        // these four symbols are only recognized at logical start of line:
        $.TABS,     // the expected indentation (only at column 0)
        $._INDENT,  // ++expected if zero-width lookahead (only at column 0)
        $._DEDENT,  // --expected if zero-width lookahead (at EOF or column 0)
        $.EPILOG,   // --expected if (expected-1) indentation with lookahead '#'
        // there is nothing the scanner can do to help with:
        $._RECOVERY // sentinel for the error condition
    ],

    rules: {

        file: $ => seq(
            field('hashbang', optional(seq('#!', $.flow))),
            field('prolog', optional(seq('#', $.flow))),
            repeat($.entry)
        ),

        dict: $ => seq(
            $._INDENT,
            field('prolog', optional(seq($.TABS, '#', $.flow))),
            repeat(seq($.TABS, $.entry)),
            $._DEDENT
        ),

        list: $ => seq(
            $._INDENT,
            field('prolog', optional(seq($.TABS, '#', $.flow))),
            repeat(seq($.TABS, $.item)),
            $._DEDENT
        ),

        utf8: $=> /[^\n]*/,
        text: $ => seq(
            $._INDENT,
            repeat(seq($.TABS, $.utf8, $.NEWLINE)),
            $._DEDENT
        ),
        flow: $ => seq($.utf8, $.NEWLINE, optional($.text)),

        entry: $ => seq(
            field('gap', optional('\n')),
            field('before', optional(seq('//', $.flow))),
            choice(
                seq('@', field('key', $.flow), $.TABS, $.item),
                seq('<', field('key', $._ANGLE), '>', $.NEWLINE, optional($.text)),
                seq('[', field('key', $._SQUARE), ']', $.NEWLINE, optional($.list)),
                seq('{', field('key', $._CURLY), '}', $.NEWLINE, optional($.dict)),
                //seq('=', /*field('key', ''),*/ /[^\n]*/), $.NEWLINE),
                seq(field('key', /[^#/<\[@{=\t\n][^\n=]*/), '=', $.flow)
            )
        ),

        item: $ => choice(
            seq('<>', $.NEWLINE, optional($.text)),
            seq('[]', $.NEWLINE, optional($.list)),
            seq('{}', $.NEWLINE, optional($.dict)),
            //seq($.NEWLINE),
            seq(/[^#/<\[@{=\t\n][^\n]*/, $.NEWLINE)
        ),

    },

});
