#include "tree_sitter/alloc.h"
#include "tree_sitter/parser.h"

enum TokenType {
    NEWLINE, // either EOF or a LF char
    // these three symbols are only recognized if column > 0:
    ANGLE,   // a key with lookahead: '>' NEWLINE
    SQUARE,  // a key with lookahead: ']' NEWLINE
    CURLY,   // a key with lookahead: '}' NEWLINE
    // these four symbols are only recognized at logical start of line:
    TABS,    // the expected indentation (only at column 0)
    INDENT,  // ++expected if zero-width lookahead (only at column 0)
    DEDENT,  // --expected if zero-width lookahead (at EOF or column 0)
    EPILOG,  // --expected if (expected-1) indentation with lookahead '#'
    // there is nothing the scanner can do to help with:
    RECOVERY // sentinel for the error condition
};

void *tree_sitter_tindalwic_external_scanner_create() {
    return ts_calloc(1, sizeof(uint32_t));
}

void tree_sitter_tindalwic_external_scanner_destroy(void *payload) {
    ts_free(payload);
}

unsigned tree_sitter_tindalwic_external_scanner_serialize(void *payload, char *buffer) {
    *(uint32_t *)buffer = *(uint32_t *)payload;
    return sizeof(uint32_t);
}

void tree_sitter_tindalwic_external_scanner_deserialize(void *payload, const char *buffer, unsigned length) {
    *(uint32_t *)payload = (length == sizeof(uint32_t)) ? *(uint32_t *)buffer : 0;
}

bool tree_sitter_tindalwic_external_scanner_scan(void *payload, TSLexer *lexer, const bool *valid_symbols) {
    uint32_t *indent = (uint32_t *)payload;

    #define DEBUG_log(...) lexer->log(lexer, __VA_ARGS__)

    if (valid_symbols[RECOVERY]) {
        DEBUG_log("scanner=>false (error recovery)");
        return false;
    }
    uint32_t start = lexer->get_column(lexer);
    DEBUG_log(
        "scanner%s%s%s%s%s%s%s%s indent=%d column=%d",
        valid_symbols[NEWLINE]?" NEWLINE":"",
        valid_symbols[ANGLE]?" ANGLE":"",
        valid_symbols[SQUARE]?" SQUARE":"",
        valid_symbols[CURLY]?" CURLY":"",
        valid_symbols[TABS]?" TABS":"",
        valid_symbols[INDENT]?" INDENT":"",
        valid_symbols[DEDENT]?" DEDENT":"",
        valid_symbols[EPILOG]?" EPILOG":"",
        *indent, start
    );

    if (lexer->eof(lexer)) {

        if (valid_symbols[DEDENT] && *indent > 0) {
            --*indent;
            lexer->result_symbol = DEDENT;
            DEBUG_log("scanner=>DEDENT (at EOF)");
            return true;
        }
        if (valid_symbols[NEWLINE]) {
            lexer->result_symbol = NEWLINE;
            DEBUG_log("scanner=>NEWLINE (at EOF)");
            return true;
        }

        DEBUG_log("scanner=>false (at EOF)");
        return false;
    }

    if (valid_symbols[NEWLINE] && lexer->lookahead == '\n') {
        lexer->advance(lexer, false);
        lexer->result_symbol = NEWLINE;
        DEBUG_log("scanner=>NEWLINE");
        return true;
    }

    lexer->mark_end(lexer); // we will be peeking ahead without growing the token

    if (start) { // not at beginning of line

        int32_t marker = valid_symbols[ANGLE] ? '>'
            : valid_symbols[SQUARE] ? ']'
            : valid_symbols[CURLY] ? '}'
            : 0;
        if (marker) {
            bool closed = false;
            while (lexer->lookahead != '\n' && !lexer->eof(lexer)) {
                if (lexer->lookahead != marker)
                    closed = false;
                else {
                    lexer->mark_end(lexer);
                    closed = true;
                }
                lexer->advance(lexer, false);
            }
            if (!closed) {
                DEBUG_log("scanner=>false (not closed)");
                return false;
            } else if (valid_symbols[ANGLE]) {
                lexer->result_symbol = ANGLE;
                DEBUG_log("scanner=>ANGLE");
                return true;
            } else if (valid_symbols[SQUARE]) {
                lexer->result_symbol = SQUARE;
                DEBUG_log("scanner=>SQUARE");
                return true;
            } else if (valid_symbols[CURLY]) {
                lexer->result_symbol = CURLY;
                DEBUG_log("scanner=>CURLY");
                return true;
            }
        }

    } else { // starting at column 0

        if (valid_symbols[TABS] && !*indent) {
            lexer->result_symbol = TABS;
            DEBUG_log("scanner=>TABS (zero-width)");
            return true;
        }
        uint32_t count = 0;
        while (lexer->lookahead == '\t'){
            lexer->advance(lexer, false);
            ++count;
            if (valid_symbols[TABS] && count == *indent) {
                lexer->mark_end(lexer);
                lexer->result_symbol = TABS;
                DEBUG_log("scanner=>TABS");
                return true;
            }
            if (valid_symbols[INDENT] && count > *indent) {
                ++*indent;
                lexer->result_symbol = INDENT;
                DEBUG_log("scanner=>INDENT");
                return true;
            }
        }
        if (valid_symbols[EPILOG] && count + 1 == *indent && lexer->lookahead == '#') {
            lexer->mark_end(lexer);
            --*indent;
            lexer->result_symbol = EPILOG;
            DEBUG_log("scanner=>EPILOG");
            return true;
        }
        if (valid_symbols[DEDENT] && *indent) {
            --*indent;
            lexer->result_symbol = DEDENT;
            DEBUG_log("scanner=>DEDENT");
            return true;
        }

    }

    DEBUG_log("scanner=>false");
    return false;
}
