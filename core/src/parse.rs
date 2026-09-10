//! everything related to converting bytes into a File

use crate::{Comment, Entries, Entry, File, Item, Items, Value};

// there are some lines/branches here that are impossible to get coverage for,
// and the mechanisms for suppressing the report are inadequate ... until:
//  + https://github.com/rust-lang/rust/issues/84605
//  + https://github.com/rust-lang/rust/issues/15701

/// parsing problems
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ParseError {
    /// a problem in the Tindalwic
    Syntax {
        /// the first line (inclusive ala Range::start)
        start: usize,
        /// one past last line (exclusive ala Range::end)
        end: usize,
        /// English description of the problem
        message: &'static str,
    },
    /// ran out of room in the storage
    Memory(
        /// English description of the problem
        &'static str,
    ),
}
impl core::error::Error for ParseError {}
impl ParseError {
    /// make a Syntax error with an arbitrary span of lines.
    pub fn new(start: usize, end: usize, message: &'static str) -> Self {
        ParseError::Syntax {
            start,
            end,
            message,
        }
    }
    /// make a Syntax error for a single line.
    pub fn at(line: usize, message: &'static str) -> Self {
        ParseError::new(line, line + 1, message)
    }
}

/// used by parser to create items
pub trait Build<'a> {
    /// push an item for a future .finish_items to use.
    fn push_item(&mut self, item: Item<'a>) -> Result<(), &'static str>;
    /// create an [Items] from the `count` most recently pushed items.
    fn finish_items(&mut self, count: usize) -> Result<Items<'a>, &'static str>;
    /// push an entry for a future .finish_entries to use.
    fn push_entry(&mut self, entry: Entry<'a>) -> Result<(), &'static str>;
    /// create an [Entries] from the `count` most recently pushed entries.
    fn finish_entries(&mut self, count: usize) -> Result<Entries<'a>, &'static str>;
    /// push an [Item::Text] (no metadata) for a future .finish_items to use.
    fn text_item(&mut self, value: &'a str) -> Result<(), &'static str> {
        self.push_item(Item::text(value))
    }
    /// push an [Item::List] (no metadata) for a future .finish_items to use.
    fn list_item(&mut self, count: usize) -> Result<(), &'static str> {
        let items = self.finish_items(count)?;
        self.push_item(Item::list(items))
    }
    /// push an [Item::Dict] (no metadata) for a future .finish_items to use.
    fn dict_item(&mut self, count: usize) -> Result<(), &'static str> {
        let entries = self.finish_entries(count)?;
        self.push_item(Item::dict(entries))
    }
    /// push a `key` -> [Item::Text] association (no metadata) for a future .finish_entries to use.
    fn text_entry(&mut self, key: &'a str, value: &'a str) -> Result<(), &'static str> {
        self.associate(key, Item::text(value))
    }
    /// push a `key` -> [Item::List] association (no metadata) for a future .finish_entries to use.
    fn list_entry(&mut self, key: &'a str, count: usize) -> Result<(), &'static str> {
        let items = self.finish_items(count)?;
        self.associate(key, Item::list(items))
    }
    /// push a `key` -> [Item::Dict] association (no metadata) for a future .finish_entries to use.
    fn dict_entry(&mut self, key: &'a str, count: usize) -> Result<(), &'static str> {
        let entries = self.finish_entries(count)?;
        self.associate(key, Item::dict(entries))
    }
    /// push a `key` -> `item` association (no metadata) for a future .finish_entries to use
    fn associate(&mut self, key: &'a str, item: Item<'a>) -> Result<(), &'static str> {
        self.push_entry(Entry {
            key: key.into(),
            item,
            ..Default::default()
        })
    }
    /// default is an Err because intern needs alloc
    #[allow(unused_variables)]
    fn intern(&mut self, value: &'_ str) -> Result<&'a str, &'static str> {
        Err("intern not supported")
    }
}

/// provide a Builder to get access to parsing
pub trait Parse<'a> {
    /// get a builder for the parser to use
    fn builder(&mut self) -> &mut dyn Build<'a>;
    /// call the parser on the provided content, with a callback for errors.
    fn report_errors(
        &mut self,
        content: &'a str,
        report: &'_ mut dyn FnMut(ParseError) -> Reported,
    ) -> Option<File<'a>> {
        Input::parse(self.builder(), content, report)
    }
    /// call the parser on the provided content, give up at first error.
    fn first_error(&mut self, content: &'a str) -> Result<File<'a>, ParseError> {
        let mut first: Option<ParseError> = None;
        self.report_errors(content, &mut |error| {
            first = Some(error);
            Reported::Abort
        })
        .ok_or_else(|| first.expect("error should have been reported"))
    }
    /// call the parser on the provided content, panic if the content isn't legit.
    fn panic_first_error(&mut self, content: &'a str) -> File<'a> {
        self.report_errors(content, &mut |error| panic!("{error}"))
            .expect("panic should have already happened in report")
    }
}

/// the "report" callback provided to the parser should return one of these
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Reported {
    /// tell parser to give up
    Abort,
    /// tell parser to keep going if it can, to find additional errors
    Continue,
}

/// start at provided offset, count tab chars.
pub(super) fn indentation(bytes: &[u8], start: usize, limit: usize) -> usize {
    let mut offset = start;
    while offset < limit && bytes[offset] == b'\t' {
        offset += 1;
    }
    offset - start
}

struct Input<'a, 'r> {
    utf8: &'a str, // entire tindalwic encoded content
    line: usize,   // the number of the current line
    start: usize,  // start of current line, `MAX` means finished
    first: usize,  // first non-tab byte of current line
    assign: usize, // the `=` on current line, `MAX` means none
    end: usize,    // the newline ending current line, or `utf8.len()`
    tabs: usize,   // indentation on this line, unless gap, then peek from next line
    report: &'r mut dyn FnMut(ParseError) -> Reported,
    good: bool,
}
impl<'a, 'r> Input<'a, 'r> {
    /// None means the arena is too small (or the UTF-8 is way too big).
    pub fn parse(
        arena: &mut dyn Build<'a>,
        utf8: &'a str,
        mut report: impl FnMut(ParseError) -> Reported + 'r,
    ) -> Option<File<'a>> {
        let mut input = Input {
            utf8,
            line: 0,
            start: 0,
            first: 0,
            assign: 0,
            end: usize::MAX, // will wrap to 0 inside `next`
            tabs: 0,
            report: &mut report,
            good: true,
        };
        if utf8.len() >= usize::MAX {
            // not covered (impossible to get, can't suppress completely).
            // MAX is a sentinel (in Value::indent), so it can't also be a length.
            // paranoid: no str can be this big (assuming usize correctly implemented),
            // but it is simple and cheap to be explicit about the contract.
            input.report(ParseError::Memory("way too big"))?;
            return None;
        }
        input.next(0)?;
        let hashbang = input.comment(0, b"#!")?;
        let prolog = input.comment(0, b"#")?;
        let cells = input.entries(0, arena)?;
        if input.start != usize::MAX {
            // not covered (impossible to get, can't suppress completely).
            // current code will always report an error in `.entries()` call above,
            // but this safety net is simple and cheap.
            input.report(ParseError::at(input.line, "unexpected leftovers"))?;
        }
        if !input.good {
            None
        } else {
            Some(File {
                hashbang,
                prolog,
                cells,
            })
        }
    }

    fn report(&mut self, err: ParseError) -> Option<()> {
        self.good = false;
        match (self.report)(err) {
            Reported::Abort => None,
            Reported::Continue => {
                if let ParseError::Memory(_) = err {
                    None
                } else {
                    Some(())
                }
            }
        }
    }

    /// done with current line, so advance, skipping excessively indented lines.
    /// usize::MAX prevents skipping. return false if finished with entire UTF-8.
    /// use `stretch` instead for Comment and Text (where no line is excessive).
    /// return None if the report signals abort.
    fn next(&mut self, indent: usize) -> Option<bool> {
        if self.start == usize::MAX {
            return Some(false);
        }
        self.line += 1;
        self.start = self.end.wrapping_add(1);
        if !self.scan()? {
            return Some(false);
        }
        if self.tabs <= indent {
            return Some(true);
        }
        let begin = self.line;
        self.line += 1;
        self.start = self.end + 1;
        while self.scan()? && self.tabs > indent {
            self.line += 1;
            self.start = self.end + 1;
        }
        self.report(ParseError::new(begin, self.line, "excess indentation"))?;
        return Some(self.start != usize::MAX);
    }

    /// helper for `next` to update state by examining a line of UTF-8.
    /// assumes caller has correctly set `self.start` (out-of-bounds is fine).
    /// return None if the report signals abort.
    fn scan(&mut self) -> Option<bool> {
        let bytes = self.utf8.as_bytes();
        let limit = bytes.len();
        let mut offset = self.start;
        if offset >= limit {
            self.start = usize::MAX;
            self.first = usize::MAX;
            self.assign = usize::MAX;
            self.tabs = 0;
            return Some(false);
        }
        offset += indentation(bytes, offset, limit);
        self.first = offset;
        self.assign = usize::MAX;
        while offset < limit && bytes[offset] != b'\n' {
            if bytes[offset] == b'=' {
                self.assign = offset;
                while offset < limit && bytes[offset] != b'\n' {
                    offset += 1;
                }
                break;
            }
            offset += 1;
        }
        self.end = offset; // never MAX because `parse` checked length
        if self.start != self.end {
            self.tabs = self.first - self.start;
            return Some(true);
        }
        // found a gap, peek ahead to figure out its virtual indentation
        offset += 1;
        if offset < limit && bytes[offset] == b'\n' {
            let begin = self.line;
            self.line += 1;
            offset += 1;
            while offset < limit && bytes[offset] == b'\n' {
                self.line += 1;
                offset += 1;
            }
            self.report(ParseError::new(begin, self.line, "consecutive empty lines"))?;
            self.start = offset - 1;
            self.first = offset - 1;
            self.end = offset - 1;
        }
        offset += indentation(bytes, offset, limit);
        self.tabs = offset - 1 - self.end;
        return Some(true);
    }

    /// current line has been recognized as beginning of a Comment or Text that might
    /// continue, so stretch it out to include the whole thing by changing `end`.
    /// return None if the report signals abort.
    fn stretch(&mut self, indent: usize, from: usize) -> Option<Value<'a>> {
        let value = Value::slice_prefix(indent, &self.utf8[from..]);
        self.end = from + value.byte_count();
        self.next(usize::MAX)?; // stretch means excess is impossible
        Some(value)
    }
    fn stretch_once(&mut self, indent: usize) -> bool {
        let bytes = self.utf8.as_bytes();
        let limit = bytes.len();
        let mut offset = self.end;
        if offset >= limit {
            return false;
        }
        debug_assert!(bytes[offset] == b'\n', "impossible: not at newline");
        let tabs = indentation(bytes, offset + 1, limit);
        if tabs < indent {
            return false;
        }
        offset += 1 + tabs;
        while offset < limit && bytes[offset] != b'\n' {
            offset += 1;
        }
        self.end = offset; // never MAX because `parse` checked length
        true
    }

    /// use this whenever a comment is allowed, returns None if current line does not
    /// have exactly the provided indent and prefix.
    fn comment(&mut self, indent: usize, prefix: &'static [u8]) -> Option<Option<Comment<'a>>> {
        if self.start == usize::MAX || self.tabs != indent {
            return Some(None);
        }
        let bytes = self.utf8.as_bytes();
        let limit = bytes.len();
        let mut from = self.first + prefix.len();
        if from > limit || &bytes[self.first..from] != prefix {
            return Some(None);
        }
        let more = indent + 1;
        if prefix == [b'#'] && from == self.end && self.stretch_once(more) {
            from += more + 1;
        }
        let value = self.stretch(more, from)?;
        Some(Some(Comment { value }))
    }

    /// current line has been recognized as beginning a Text, from a `<>` context on
    /// the previous line, or from shortcut syntax. `from` says where text begins.
    /// lenient - one-liners can stretch.
    fn text(&mut self, indent: usize, from: usize) -> Option<Item<'a>> {
        let value = self.stretch(indent + 1, from)?;
        let epilog = self.comment(indent, b"#")?;
        Some(Item::Text { value, epilog })
    }
    /// text block follows current line. block might have zero lines.
    fn text_block(&mut self, indent: usize) -> Option<Item<'a>> {
        let end = self.end;
        if !self.stretch_once(indent + 1) {
            // zero lines in this block, take empty slice from this line
            self.text(indent, end)
        } else {
            // first line of stretched text can have excess indent
            self.text(indent, end + indent + 2)
        }
    }

    /// previous line opened a list context, so parse all the lines in it.
    fn list(&mut self, indent: usize, arena: &mut dyn Build<'a>) -> Option<Item<'a>> {
        Some(Item::List {
            prolog: self.comment(indent + 1, b"#")?,
            cells: self.items(indent + 1, arena)?,
            epilog: self.comment(indent, b"#")?,
        })
    }
    fn items(&mut self, indent: usize, arena: &mut dyn Build<'a>) -> Option<Items<'a>> {
        let bytes = self.utf8.as_bytes();
        let mut count = 0usize;
        while self.start != usize::MAX {
            let mut item: Option<Item<'a>> = None;
            if self.start == self.end || self.tabs != indent {
                break;
            } else if self.first >= self.end {
                // indentation-only is the shortcut for empty text
                // TODO maybe too easily confused with gaps (require explicit `<>`)?
                item = Some(self.text(indent, self.end)?);
            } else {
                let len = self.end - self.first;
                match bytes[self.first] {
                    b'#' => {
                        self.report(ParseError::at(self.line, "stray `#` comment"))?;
                        self.comment(indent, b"#")?; // read and throw away
                    }
                    b'/' => {
                        self.report(ParseError::at(
                            self.line,
                            if len < 2 || bytes[self.first + 1] != b'/' {
                                "malformed // comment"
                            } else {
                                "no // comments in lists"
                            },
                        ))?;
                        self.comment(indent, b"/")?; // read and throw away
                    }
                    b'<' => {
                        if len != 2 || bytes[self.end - 1] != b'>' {
                            self.report(ParseError::at(self.line, "malformed `<>` in list"))?;
                            self.next(indent)?;
                        } else {
                            item = Some(self.text_block(indent)?);
                        }
                    }
                    b'[' => {
                        if len != 2 || bytes[self.end - 1] != b']' {
                            self.report(ParseError::at(self.line, "malformed `[]` in list"))?;
                            self.next(indent)?;
                        } else {
                            self.next(indent + 1)?;
                            item = Some(self.list(indent, arena)?);
                        }
                    }
                    b'{' => {
                        if len != 2 || bytes[self.end - 1] != b'}' {
                            self.report(ParseError::at(self.line, "malformed `{}` in list"))?;
                            self.next(indent)?;
                        } else {
                            self.next(indent + 1)?;
                            item = Some(self.dict(indent, arena)?);
                        }
                    }
                    _ => {
                        item = Some(self.text(indent, self.start + indent)?);
                    }
                }
            }
            if let Some(item) = item {
                if let Err(err) = arena.push_item(item) {
                    self.report(ParseError::Memory(err))?;
                }
                count += 1;
            }
        }
        if count == 0 {
            Some(&[])
        } else {
            match arena.finish_items(count) {
                Ok(cells) => Some(cells),
                Err(err) => {
                    self.report(ParseError::Memory(err))?;
                    None
                }
            }
        }
    }

    /// previous line opened a dict context, so parse all the lines in it.
    fn dict(&mut self, indent: usize, arena: &mut dyn Build<'a>) -> Option<Item<'a>> {
        Some(Item::Dict {
            prolog: self.comment(indent + 1, b"#")?,
            cells: self.entries(indent + 1, arena)?,
            epilog: self.comment(indent, b"#")?,
        })
    }
    fn entries(&mut self, indent: usize, arena: &mut dyn Build<'a>) -> Option<Entries<'a>> {
        let bytes = self.utf8.as_bytes();
        let mut count = 0usize;
        while self.start != usize::MAX {
            let mut item: Option<Item<'a>> = None;
            let gap = self.tabs == indent && self.first == self.end;
            if gap {
                self.next(indent)?;
            }
            let before = self.comment(indent, b"//")?;
            if self.start == usize::MAX || self.tabs != indent {
                if gap || before.is_some() {
                    self.report(ParseError::at(self.line, "gap/before but no key"))?;
                }
                break;
            }
            let mut key: Value<'a> = Value::default();
            let len = self.end - self.first;
            match bytes[self.first] {
                b'#' => {
                    self.report(ParseError::at(self.line, "stray `#` comment"))?;
                    self.comment(indent, b"#")?; // read and throw away
                }
                b'/' => {
                    self.report(ParseError::at(
                        self.line,
                        if len < 2 || bytes[self.first + 1] != b'/' {
                            "malformed // comment"
                        } else {
                            "stray `//` comment"
                        },
                    ))?;
                    self.comment(indent, b"/")?; // read and throw away
                }
                b'<' => {
                    if len < 2 || bytes[self.end - 1] != b'>' {
                        self.report(ParseError::at(self.line, "malformed `<key>` in dict"))?;
                        self.next(indent)?;
                    } else {
                        key = self.utf8[self.first + 1..self.end - 1].into();
                        item = Some(self.text_block(indent)?);
                    }
                }
                b'[' => {
                    if len < 2 || bytes[self.end - 1] != b']' {
                        self.report(ParseError::at(self.line, "malformed `[key]` in dict"))?;
                        self.next(indent)?;
                    } else {
                        key = self.utf8[self.first + 1..self.end - 1].into();
                        self.next(indent + 1)?;
                        item = Some(self.list(indent, arena)?);
                    }
                }
                b'@' => {
                    key = self.stretch(indent + 1, self.first + 1)?;
                    let marker = if self.end > 1 && self.first == self.end - 2 {
                        (bytes[self.first], bytes[self.first + 1])
                    } else {
                        (0u8, 0u8)
                    };
                    match marker {
                        (b'<', b'>') => {
                            item = Some(self.text_block(indent)?);
                        }
                        (b'[', b']') => {
                            self.next(indent + 1)?;
                            item = Some(self.list(indent, arena)?);
                        }
                        (b'{', b'}') => {
                            self.next(indent + 1)?;
                            item = Some(self.dict(indent, arena)?);
                        }
                        _ => {
                            self.report(ParseError::at(
                                self.line,
                                "must have `<>`, `[]` or `{}` after @multi-line-key",
                            ))?;
                            self.next(indent)?;
                        }
                    }
                }
                b'{' => {
                    if len < 2 || bytes[self.end - 1] != b'}' {
                        self.report(ParseError::at(self.line, "malformed `{key}` in dict"))?;
                        self.next(indent)?;
                    } else {
                        key = self.utf8[self.first + 1..self.end - 1].into();
                        self.next(indent + 1)?;
                        item = Some(self.dict(indent, arena)?);
                    }
                }
                b'\t' => {
                    self.report(ParseError::at(self.line, "excess indentation?"))?;
                    self.next(indent)?;
                }
                _ => {
                    if self.assign == usize::MAX {
                        self.report(ParseError::at(self.line, "missing `=` in dict"))?;
                        self.next(indent)?;
                    } else {
                        key = self.utf8[self.first..self.assign].into();
                        item = Some(self.text(indent, self.assign + 1)?);
                    }
                }
            }
            if let Some(item) = item {
                if let Err(err) = arena.push_entry(Entry {
                    gap,
                    before,
                    key,
                    item,
                }) {
                    self.report(ParseError::Memory(err))?;
                }
                count += 1;
            } else if gap || before.is_some() {
                self.report(ParseError::at(self.line, "gap/before but no item"))?;
            }
        }
        if count == 0 {
            Some(&[])
        } else {
            match arena.finish_entries(count) {
                Ok(cells) => Some(cells),
                Err(err) => {
                    self.report(ParseError::Memory(err))?;
                    None
                }
            }
        }
    }
}
