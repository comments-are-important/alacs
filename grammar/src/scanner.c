#include "tree_sitter/alloc.h"
#include "tree_sitter/parser.h"
#include <string.h>

typedef struct {
    uint32_t margin;
} TindalwicScanner;

void *tree_sitter_tindalwic_external_scanner_create() {
    return ts_malloc(sizeof(TindalwicScanner));
}

void tree_sitter_tindalwic_external_scanner_destroy(void *payload) {
    ts_free(payload);
}

unsigned tree_sitter_tindalwic_external_scanner_serialize(void *payload, char *buffer) {
    memcpy(buffer, payload, sizeof(TindalwicScanner));
    return sizeof(TindalwicScanner);
}

void tree_sitter_tindalwic_external_scanner_deserialize(void *payload, const char *buffer, unsigned length) {
    if (length == sizeof(TindalwicScanner))
        memcpy(payload, buffer, sizeof(TindalwicScanner));
    else {
        TindalwicScanner *scanner = (TindalwicScanner *)payload;
        scanner->margin = UINT32_MAX;
    }
}

// don't edit the token list here, copy-n-paste from grammar, strip prefixes, then
// copy-n-paste-n-tweak to the big `DEBUG_log` near top of scan and count the `%s`.
// make sure INDENT/DEDENT stay straddling the demarcation of exclusive tokens.
enum TindalwicToken {
        // most tokens are mutually exclusive: grammar rules must
        // never ask for more than one from any single scanner call.
        NEW_LINE,    // LF or zero-width beginning of file
        MARGIN,      // the expected number of TABs starting at column 0
        SHORT_STR,   // empty or /[^#/@=<>{}\[\]\n\t][^\n]*/
        SHORT_KEY,   // empty or /[^#/@=<>{}\[\]\n\t][^=\n]*/ if peek('=')
        TEXT_KEY,    // rest of line if peek('>', EOF or LF)
        DICT_KEY,    // rest of line if peek('}', EOF or LF)
        LIST_KEY,    // rest of line if peek(']', EOF or LF)
        INDENT,      // ++margin zero-width
        // remaining tokens help the rules determine the structure: scanner
        // will be asked to select from among more than one of them.
        // until issue 5929 gets done all these must be zero-width
        DEDENT,      // --margin if EOF or peek(LF, not enough TABs)
        PEEK_EMPTY,  // if peek(NEW_LINE, EOF or LF)
        PEEK_MARGIN, // if peek(NEW_LINE, margin TABS)
};

static bool special_char(int32_t ch) {
    switch (ch) {
        case '\n': case '\t': case '#': case '/': case '@': case '=':
        case '<': case '>': case '[': case ']': case '{': case '}':
            return true;
    }
    return false;
}

static bool key_closed(char marker, TSLexer *lexer) {
    bool closed = false;
    while (lexer->lookahead != '\n' && !lexer->eof(lexer)) {
        if (lexer->lookahead != marker) closed = false;
        else { lexer->mark_end(lexer); closed = true; }
        lexer->advance(lexer, false); }
    return closed;
}

bool tree_sitter_tindalwic_external_scanner_scan(void *payload, TSLexer *lexer, const bool *valid_symbols) {
    TindalwicScanner *scanner = (TindalwicScanner *)payload;
    bool beginning = scanner->margin == UINT32_MAX;
    unsigned exclusive = 0;
    for (enum TindalwicToken token = 0 ; token < DEDENT ; ++token)
        if (valid_symbols[token])
            ++exclusive;

    #define DEBUG_log(...) lexer->log(lexer, __VA_ARGS__)
    if (exclusive > 1) {
        DEBUG_log(
            "scanner.%u%s =>false (%s)",
            beginning?0:scanner->margin, beginning?"*":"",
            (exclusive == DEDENT)?"error recovery":"exclusivity violation - fix grammar"
        );
        return false;
    }
    DEBUG_log(
        "scanner.%u%s %s%s%s%s%s%s%s%s%s%s%s %s",
        beginning?0:scanner->margin, beginning?"*":"",
        valid_symbols[NEW_LINE]?" NEW_LINE":"",
        valid_symbols[MARGIN]?" MARGIN":"",
        valid_symbols[SHORT_STR]?" SHORT_STR":"",
        valid_symbols[SHORT_KEY]?" SHORT_KEY":"",
        valid_symbols[TEXT_KEY]?" TEXT_KEY":"",
        valid_symbols[DICT_KEY]?" DICT_KEY":"",
        valid_symbols[LIST_KEY]?" LIST_KEY":"",
        valid_symbols[INDENT]?" INDENT":"",
        valid_symbols[DEDENT]?" DEDENT":"",
        valid_symbols[PEEK_EMPTY]?" PEEK_EMPTY":"",
        valid_symbols[PEEK_MARGIN]?" PEEK_MARGIN":"",
        ":"
    );

    #define RETURN_false(...) { \
        DEBUG_log("scanner =>false" __VA_ARGS__); \
        return false; }
    #define RETURN_true(symbol, ...) { \
        DEBUG_log("scanner =>" #symbol __VA_ARGS__); \
        lexer->result_symbol = symbol; \
        return true; }

    if (valid_symbols[NEW_LINE]) {
        if (beginning) {
            scanner->margin = 0;
            RETURN_true(NEW_LINE, " (virtual at beginning of file)");
        }
        if (lexer->lookahead != '\n')
            RETURN_false(" (NEW_LINE must follow PEEK_MARGIN|PEEK_EMPTY - fix grammar)");
        lexer->advance(lexer, false);
        RETURN_true(NEW_LINE);
    }
    if (beginning) {
        if (!(valid_symbols[PEEK_MARGIN] && valid_symbols[PEEK_EMPTY]))
            RETURN_false(" (must begin with PEEK_MARGIN|PEEK_EMPTY - fix grammar)");
        if (lexer->eof(lexer))
            RETURN_false(" (empty file)");
        if (lexer->lookahead == '\n')
            RETURN_true(PEEK_EMPTY, " (at beginning of file)");
        RETURN_true(PEEK_MARGIN, " (at beginning of file)");
    }

    lexer->mark_end(lexer); // we will be doing a lot of peeking ahead

    if (valid_symbols[MARGIN]) {
        uint32_t column = lexer->get_column(lexer);
        if (column != 0)
            RETURN_false(" (rule asking for margin at column %u - fix grammar)", column);
        for (uint32_t need = scanner->margin ; need != 0 ; --need) {
            // peek/dedent code duplicates loop and the `if` that follows (keep in sync)
            if (lexer->lookahead == '\t') {
                lexer->advance(lexer, false);
                continue;
            }
            RETURN_false(" (non-TAB 0x%X)", lexer->lookahead);
        }
        lexer->mark_end(lexer);
        RETURN_true(MARGIN);
    }
    if (valid_symbols[SHORT_STR]) {
        if (lexer->eof(lexer))
            RETURN_true(SHORT_STR, " (at EOF)");
        if (lexer->lookahead == '\n')
            RETURN_true(SHORT_STR, " (at EOL)");
        if (special_char(lexer->lookahead))
            RETURN_false(" (1st char is reserved)");
        lexer->advance(lexer, false);
        while (lexer->lookahead != '\n' && !lexer->eof(lexer))
            lexer->advance(lexer, false);
        lexer->mark_end(lexer);
        RETURN_true(SHORT_STR);
    }
    if (valid_symbols[SHORT_KEY]) {
        if (lexer->eof(lexer))
            RETURN_true(SHORT_KEY, " (at EOF)");
        if (lexer->lookahead == '\n')
            RETURN_true(SHORT_KEY, " (at EOL)");
        if (special_char(lexer->lookahead))
            RETURN_false(" (1st char is reserved)");
        lexer->advance(lexer, false);
        while (lexer->lookahead != '\n' && !lexer->eof(lexer)) {
            if (lexer->lookahead == '=') {
                lexer->mark_end(lexer);
                RETURN_true(SHORT_KEY);
            }
            lexer->advance(lexer, false);
        }
        RETURN_false(" (missing '=' after short key)");
    }
    if (valid_symbols[TEXT_KEY]) {
        if (!key_closed('>', lexer))
            RETURN_false(" (not closed)");
        RETURN_true(TEXT_KEY);
    }
    if (valid_symbols[DICT_KEY]) {
        if (!key_closed('}', lexer))
            RETURN_false(" (not closed)");
        RETURN_true(DICT_KEY);
    }
    if (valid_symbols[LIST_KEY]) {
        if (!key_closed(']', lexer))
            RETURN_false(" (not closed)");
        RETURN_true(LIST_KEY);
    }

    if (valid_symbols[INDENT]) {
        if (scanner->margin >= UINT32_MAX - 1)
            RETURN_false(" (excessive INDENT)");
        ++scanner->margin;
        RETURN_true(INDENT);
    }

    if (exclusive != 0)
        RETURN_false(" (exclusive should be handled before this point - fix scanner)");

    if (lexer->eof(lexer)) {
        if (valid_symbols[DEDENT]) {
            if (scanner->margin == 0)
                RETURN_false(" (unbalanced DEDENT)");
            --scanner->margin;
            RETURN_true(DEDENT, " (at EOF)");
        }
        RETURN_false(" (at EOF)");
    }
    if (lexer->lookahead != '\n')
        RETURN_false(" (peek/dedent at LF, not 0x%X - fix grammar)", lexer->lookahead);
    lexer->advance(lexer, false);
    if (valid_symbols[PEEK_EMPTY] && lexer->lookahead == '\n')
        RETURN_true(PEEK_EMPTY);
    for (uint32_t need = scanner->margin ; need != 0 ; --need) {
        // MARGIN code duplicates loop and the `if` that follows (keep in sync)
        if (lexer->lookahead == '\t') {
            lexer->advance(lexer, false);
            continue;
        }
        if (!valid_symbols[DEDENT])
            RETURN_false(" (insufficient TABs but DEDENT not valid? - check grammar)");
        if (scanner->margin == 0)
            RETURN_false(" (unbalanced DEDENT)");
        --scanner->margin;
        RETURN_true(DEDENT);
    }
    if (valid_symbols[PEEK_MARGIN])
        RETURN_true(PEEK_MARGIN);
    RETURN_false(" (nothing matched)");
}
