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

static bool reserved_char(int32_t ch) {
    switch (ch) {
        case '\n': case '\t': case '#': case '/': case '@': case '=':
        case '<': case '>': case '[': case ']': case '{': case '}':
            return true;
    }
    return false;
}

enum TindalwicToken {
    // first 5 tokens are about structure and may be `valid_symbols` in any call...
    NEW_LINE,   // LF or zero-width beginning of file
    MARGIN,     // the expected number of TAB chars starting at column 0
    INDENT,     // zero-width ++margin if peek: LF + more TABs than expected
    DEDENT,     // zero-width --margin if EOF or peek: LF + insufficient TABs
    EMPTY_LINE, // NEW_LINE with peek: LF (but not EOF)
    // these 5 tokens are mutually exclusive with each other (but not those above)...
    SHORT_ITEM, // empty or /[^[:reserved_char:]][^\n]*/
    SHORT_KEY,  // empty or /[^[:reserved_char:]][^=\n]*/
    TEXT_KEY,   // $.line if peek: '>' + (EOF|LF)
    LIST_KEY,   // $.line if peek: ']' + (EOF|LF)
    DICT_KEY,   // $.line if peek: '}' + (EOF|LF)
    // the last token must not be used by any rules in the grammar...
    RECOVERY    // sentinel indicating error recovery
    // changes to anything above needs to be synched to:
    //  + externals in grammar (copy-n-paste from here then add `$.` prefix)
    //  + the long repeated `%s%s...%s%s` printf specifiers and the arguments
    //  + the `count_exclusive` function immediately below
};

static int count_exclusive(const bool *valid_symbols) {
    return (valid_symbols[SHORT_ITEM] + valid_symbols[SHORT_KEY]
        + valid_symbols[TEXT_KEY] + valid_symbols[LIST_KEY] + valid_symbols[DICT_KEY]);
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
        "scanner.%d%s %s%s%s%s%s%s%s%s%s%s%s",
        beginning?0:scanner->margin, beginning?"*":"",
        valid_symbols[NEW_LINE]?" NEW_LINE":"",
        valid_symbols[MARGIN]?" MARGIN":"",
        valid_symbols[INDENT]?" INDENT":"",
        valid_symbols[DEDENT]?" DEDENT":"",
        valid_symbols[EMPTY_LINE]?" EMPTY_LINE":"",
        valid_symbols[SHORT_ITEM]?" SHORT_ITEM":"",
        valid_symbols[SHORT_KEY]?" SHORT_KEY":"",
        valid_symbols[TEXT_KEY]?" TEXT_KEY":"",
        valid_symbols[LIST_KEY]?" LIST_KEY":"",
        valid_symbols[DICT_KEY]?" DICT_KEY":"",
        valid_symbols[RECOVERY]?" RECOVERY":""
    );

    #define RETURN_false(...) { \
        DEBUG_log("scanner =>false" __VA_ARGS__); \
        return false; }
    #define RETURN_true(symbol, ...) { \
        DEBUG_log("scanner =>" #symbol __VA_ARGS__); \
        lexer->result_symbol = symbol; \
        return true; }

    lexer->mark_end(lexer); // we will be doing a lot of peeking ahead

    if (beginning) {
        if (lexer->eof(lexer))
            RETURN_false(" (empty file)");
        if (valid_symbols[EMPTY_LINE] && lexer->lookahead == '\n') {
            scanner->margin = 0;
            RETURN_true(EMPTY_LINE, " (at beginning)");
        }
        if (valid_symbols[NEW_LINE]) {
            scanner->margin = 0;
            RETURN_true(NEW_LINE);
        }
        RETURN_false(" (beginning must NEW_LINE/EMPTY_LINE - fix grammar rules)");
    }

    if (count_exclusive(valid_symbols) > 1)
        // it's very difficult to know which symbols will be requested together: an edit
        // to the rules that seems innocuous could introduce an exclusivity violation.
        // better to have a clear log message than let the code stumble through an
        // inconsistent series of advance/lookahead/mark_end steps.
        RETURN_false(" (more than one exclusive symbol requested - fix grammar rules)");

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
        while (lexer->lookahead != '\n' && lexer->lookahead != '=' && !lexer->eof(lexer))
            lexer->advance(lexer, false);
        lexer->mark_end(lexer);
        RETURN_true(SHORT_KEY);
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
    if (lexer->get_column(lexer) != 0)
        RETURN_false(" (column=%d != 0)", lexer->get_column(lexer));
    if (valid_symbols[EMPTY_LINE] && linefeed && lexer->lookahead == '\n') {
        lexer->mark_end(lexer);
        RETURN_true(EMPTY_LINE);
    }
    if (valid_symbols[NEW_LINE] && linefeed) {
        lexer->mark_end(lexer);
        RETURN_true(NEW_LINE);
    }
    uint32_t tabs = 0;
    for ( ; tabs != scanner->margin && lexer->lookahead == '\t' ; ++tabs)
        lexer->advance(lexer, false);
    if (lexer->get_column(lexer) != tabs)
        RETURN_false(" (column=%d != %d)", lexer->get_column(lexer), tabs);
    if (valid_symbols[DEDENT] && tabs != scanner->margin) {
        if (scanner->margin == 0)
            RETURN_false(" (unbalanced DEDENT)");
        --scanner->margin;
        RETURN_true(DEDENT);
    }
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

    RETURN_false(" (nothing matched)");
}
