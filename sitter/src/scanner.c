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

enum TindalwicToken {
    // don't edit the token list here, copy-n-paste from grammar, strip prefixes, then
    // copy-n-paste-n-tweak to the big `DEBUG_log` near top of scan and count the `%s`.
        NEW_LINE,  // LF or zero-width beginning of file
        MARGIN,    // the expected number of TAB chars starting at column 0
        SHORT_ITEM, // empty or /[^[:reserved_char:]][^\n]*/
        SHORT_KEY,  // empty or /[^[:reserved_char:]][^=\n]*/ if peek: '='
        TEXT_KEY,   // rest of line if peek: '>' + (EOF|LF)
        LIST_KEY,   // rest of line if peek: ']' + (EOF|LF)
        DICT_KEY,   // rest of line if peek: '}' + (EOF|LF)
        // sentinel marks end of exclusive group, must not be used in any rule
        RECOVERY,   // indicates error condition call
        // remaining tokens help the rules determine the structure so scanner will be
        // asked to select from among them (sometimes one but often multiple).
        TRUTHY,    // zero-width if peek: NEW_LINE+!LF
        FALSY,     // zero-width if peek: NEW_LINE+LF
        INDENT,     // zero-width ++margin if peek: LF + more TABs than expected
        DEDENT,     // zero-width --margin if EOF or peek: LF + insufficient TABs
        CONTINUE,   // zero-width no-op if peek: LF + margin TABs (or more)
};

static bool reserved_char(int32_t ch) {
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

    #define DEBUG_log(...) lexer->log(lexer, __VA_ARGS__)
    if (valid_symbols[RECOVERY]) {
        DEBUG_log(
            "scanner.%d%s =>false (error recovery)",
            beginning?0:scanner->margin, beginning?"*":""
        );
        return false;
    }
    DEBUG_log(
        "scanner.%d%s %s%s%s%s%s%s%s%s%s%s%s%s %s",
        beginning?0:scanner->margin, beginning?"*":"",
        valid_symbols[NEW_LINE]?" NEW_LINE":"",
        valid_symbols[MARGIN]?" MARGIN":"",
        valid_symbols[SHORT_ITEM]?" SHORT_ITEM":"",
        valid_symbols[SHORT_KEY]?" SHORT_KEY":"",
        valid_symbols[TEXT_KEY]?" TEXT_KEY":"",
        valid_symbols[LIST_KEY]?" LIST_KEY":"",
        valid_symbols[DICT_KEY]?" DICT_KEY":"",
        valid_symbols[TRUTHY]?" TRUTHY":"",
        valid_symbols[FALSY]?" FALSY":"",
        valid_symbols[INDENT]?" INDENT":"",
        valid_symbols[DEDENT]?" DEDENT":"",
        valid_symbols[CONTINUE]?" CONTINUE":"",
        ":"
    );

    #define RETURN_false(...) { \
        DEBUG_log("scanner =>false" __VA_ARGS__); \
        return false; }
    #define RETURN_true(symbol, ...) { \
        DEBUG_log("scanner =>" #symbol __VA_ARGS__); \
        lexer->result_symbol = symbol; \
        return true; }

    bool exclusive = false;
    // it's very difficult to know which symbols will be requested together: an edit
    // to the rules that seems innocuous could introduce an exclusivity violation.
    // better to have a clear log message than let the code paint itself into a corner
    // with a series of advance/lookahead/mark_end steps that can't be rolled back.
    for (enum TindalwicToken token = 0 ; token < RECOVERY ; ++token) {
        if (!valid_symbols[token]) continue;
        if (exclusive)
            RETURN_false(" (multiple exclusive symbols requested - fix grammar)");
        exclusive = true;
    }

    lexer->mark_end(lexer); // we will be doing a lot of peeking ahead

    if (valid_symbols[NEW_LINE]) {
        if (beginning) {
            scanner->margin = 0;
            RETURN_true(NEW_LINE, " (virtual at beginning of file)");
        }
        if (lexer->lookahead != '\n')
            RETURN_false(" (NEW_LINE only allowed after TRUTHY|FALSY - fix grammar)");
        lexer->advance(lexer, false);
        lexer->mark_end(lexer);
        RETURN_true(NEW_LINE);
    }

    if (beginning) {
        if (!(valid_symbols[TRUTHY] && valid_symbols[FALSY]))
            RETURN_false(" (must begin with TRUTHY+FALSY - fix grammar)");
        if (lexer->eof(lexer))
            RETURN_false(" (empty file)");
        if (lexer->lookahead == '\n')
            RETURN_true(FALSY, " (at beginning of file)");
        RETURN_true(TRUTHY, " (at beginning of file)");
    }

    if (valid_symbols[MARGIN]) {
        for (uint32_t need = scanner->margin ; need > 0 ; lexer->advance(lexer, false), --need)
            if (lexer->lookahead != '\t')
                RETURN_false(" (non-TAB 0x%X)", lexer->lookahead);
        lexer->mark_end(lexer);
        RETURN_true(MARGIN);
    }

    if (valid_symbols[SHORT_ITEM]) {
        if (lexer->eof(lexer))
            RETURN_true(SHORT_ITEM, " (at EOF)");
        if (lexer->lookahead == '\n')
            RETURN_true(SHORT_ITEM, " (at EOL)");
        if (reserved_char(lexer->lookahead))
            RETURN_false(" (1st char is reserved)");
        lexer->advance(lexer, false);
        while (lexer->lookahead != '\n' && !lexer->eof(lexer))
            lexer->advance(lexer, false);
        lexer->mark_end(lexer);
        RETURN_true(SHORT_ITEM);
    }
    if (valid_symbols[SHORT_KEY]) {
        if (lexer->eof(lexer))
            RETURN_true(SHORT_KEY, " (at EOF)");
        if (lexer->lookahead == '\n')
            RETURN_true(SHORT_KEY, " (at EOL)");
        if (reserved_char(lexer->lookahead))
            RETURN_false(" (1st char is reserved)");
        lexer->advance(lexer, false);
        while (lexer->lookahead != '\n' && !lexer->eof(lexer)) {
            if (lexer->lookahead == '=') {
                lexer->mark_end(lexer);
                RETURN_true(SHORT_KEY);
            }
            lexer->advance(lexer, false);
        }
        RETURN_false(" (missing '=' after short key)")
    }
    if (valid_symbols[TEXT_KEY]) {
        if (!key_closed('>', lexer))
            RETURN_false(" (not closed)");
        RETURN_true(TEXT_KEY);
    }
    if (valid_symbols[LIST_KEY]) {
        if (!key_closed(']', lexer))
            RETURN_false(" (not closed)");
        RETURN_true(LIST_KEY);
    }
    if (valid_symbols[DICT_KEY]) {
        if (!key_closed('}', lexer))
            RETURN_false(" (not closed)");
        RETURN_true(DICT_KEY);
    }

    if (lexer->eof(lexer)) {
        if (valid_symbols[DEDENT]) {
            if (scanner->margin == 0)
                RETURN_false(" (unbalanced DEDENT)")
            --scanner->margin;
            RETURN_true(DEDENT, " (at EOF)");
        }
        RETURN_false(" (at EOF)");
    }
    bool linefeed = lexer->lookahead == '\n';
    if (linefeed) // kinda hacky way to share TAB counting code for all valid_symbols
        lexer->advance(lexer, false);
    else if (lexer->get_column(lexer) != 0)
        RETURN_false(" (column=%d != 0)", lexer->get_column(lexer));
    uint32_t tabs = 0;
    for ( ; tabs != scanner->margin && lexer->lookahead == '\t' ; ++tabs)
        lexer->advance(lexer, false);
    if (valid_symbols[DEDENT] && tabs != scanner->margin) {
        if (scanner->margin == 0)
            RETURN_false(" (unbalanced DEDENT)");
        --scanner->margin;
        RETURN_true(DEDENT);
    }
    if (valid_symbols[CONTINUE])
        RETURN_true(CONTINUE);
    if (valid_symbols[INDENT] && tabs == scanner->margin && lexer->lookahead == '\t') {
        if (scanner->margin >= UINT32_MAX - 1)
            RETURN_false(" (excessive INDENT)");
        ++scanner->margin;
        RETURN_true(INDENT);
    }
    if (valid_symbols[MARGIN] && tabs == scanner->margin && !linefeed) {
        lexer->mark_end(lexer);
        RETURN_true(MARGIN);
    }
    if (linefeed) {
        if (valid_symbols[FALSY] && lexer->lookahead == '\n')
            RETURN_true(FALSY);
        if (valid_symbols[TRUTHY])
            RETURN_true(TRUTHY);
    }

    RETURN_false(" (nothing matched)");
}
