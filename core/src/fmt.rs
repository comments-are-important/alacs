//! code for encoding data into the Tindalwic format.

use crate::Value;
use crate::parse::ParseError;
use crate::walk::PathError;
use crate::{Comment, Entry, File, Item};

use core::cell::Cell;
use core::fmt::{Display, Formatter, Result, Write};
use core::write;

impl Display for ParseError {
    fn fmt(&self, out: &mut Formatter<'_>) -> Result {
        match self {
            ParseError::Memory(message) => write!(out, "0: error: {message}"),
            ParseError::Syntax {
                start,
                end,
                message,
            } => {
                let last = end - 1;
                if *start >= last {
                    write!(out, "{start}: error: {message}")
                } else {
                    write!(out, "{start}: error: (thru line {last}) {message}")
                }
            }
        }
    }
}
impl<'p> Display for PathError<'p> {
    fn fmt(&self, out: &mut Formatter<'_>) -> Result {
        out.write_str("walk (")?;
        for branch in self.failed {
            match branch {
                crate::walk::Branch::Item(at) => write!(out, "[{}]", at)?,
                crate::walk::Branch::Entry(key) => write!(out, "{{{}}}", key)?,
                crate::walk::Branch::Text => out.write_str("Text")?,
                crate::walk::Branch::List => out.write_str("List")?,
                crate::walk::Branch::Dict => out.write_str("Dict")?,
            }
        }
        out.write_str("): ")?;
        out.write_str(self.message)?;
        Ok(())
    }
}

/// the string value (without indentation, *not* the encoded form).
impl<'a> Display for Value<'a> {
    fn fmt(&self, out: &mut Formatter<'_>) -> Result {
        if let Some(verbatim) = self.verbatim(0) {
            out.write_str(verbatim)
        } else {
            let mut lines = self.lines();
            if let Some(first) = lines.next() {
                out.write_str(first)?;
                for line in lines {
                    out.write_char('\n')?;
                    out.write_str(line)?;
                }
            }
            Ok(())
        }
    }
}

impl<'a> Display for File<'a> {
    fn fmt(&self, out: &mut Formatter<'_>) -> Result {
        Output { out, indent: 0 }.file(self)
    }
}

struct Output<'o, 'f> {
    out: &'o mut Formatter<'f>,
    indent: usize,
}
impl<'o, 'f> Output<'o, 'f> {
    fn indent(&mut self) -> Result {
        for _ in 0..self.indent {
            self.out.write_char('\t')?;
        }
        Ok(())
    }
    const fn special_first(byte: u8) -> bool {
        matches!(
            byte,
            b'\t' | b'#' | b'<' | b'>' | b'@' | b'[' | b']' | b'{' | b'}' | b'/' | b'='
        )
    }
    fn string<'a>(&mut self, value: &Value<'a>) -> Result {
        if let Some(slice) = value.verbatim(self.indent) {
            self.out.write_str(slice)?;
            self.out.write_char('\n')?;
        } else {
            let mut lines = value.lines();
            if let Some(first) = lines.next() {
                self.out.write_str(first)?;
                self.out.write_char('\n')?;
                for line in lines {
                    self.indent()?;
                    self.out.write_str(line)?;
                    self.out.write_char('\n')?;
                }
            } else {
                self.out.write_char('\n')?;
            }
        }
        Ok(())
    }
    fn some_comment<'a>(&mut self, marker: &'a str, comment: &Comment<'a>) -> Result {
        self.indent()?;
        self.out.write_str(marker)?;
        if comment.value.is_empty() {
            self.out.write_char('\n')?;
        } else {
            self.indent += 1;
            if marker == "#" && (comment.value.starts_with('!') || comment.value.starts_with('\n'))
            {
                self.out.write_char('\n')?;
                self.indent()?;
            }
            self.string(&comment.value)?;
            self.indent -= 1;
        }
        Ok(())
    }
    fn comment<'a>(&mut self, marker: &'a str, option: &Option<Comment<'a>>) -> Result {
        if let Some(comment) = option {
            self.some_comment(marker, comment)?;
        }
        Ok(())
    }

    fn one_liner_in_list<'a>(value: &Value<'a>) -> Option<&'a str> {
        let only = value.only_line()?;
        if value.is_empty() {
            Some(only)
        } else if Output::special_first(only.as_bytes()[0]) {
            None
        } else {
            Some(only)
        }
    }

    fn one_liner_in_dict<'a>(value: &Value<'a>, key: &'_ str) -> Option<&'a str> {
        let only = value.only_line()?;
        if key.is_empty() {
            Some(only)
        } else if key.contains('=') {
            None
        } else if Output::special_first(key.as_bytes()[0]) {
            None
        } else {
            Some(only)
        }
    }

    fn item_in_list<'a>(&mut self, cell: &Cell<Item<'a>>) -> Result {
        let item = cell.get();
        match &item {
            Item::Text { value, epilog } => {
                self.indent()?;
                if let Some(slice) = Output::one_liner_in_list(value) {
                    self.out.write_str(slice)?;
                    self.out.write_char('\n')?;
                } else {
                    self.out.write_str("<>\n")?;
                    self.indent += 1;
                    self.indent()?;
                    self.string(value)?;
                    self.indent -= 1;
                }
                self.comment("#", epilog)
            }
            Item::List {
                prolog,
                cells,
                epilog,
            } => {
                self.indent()?;
                self.out.write_str("[]\n")?;
                self.indent += 1;
                self.comment("#", prolog)?;
                for cell in *cells {
                    self.item_in_list(cell)?;
                }
                self.indent -= 1;
                self.comment("#", epilog)
            }
            Item::Dict {
                prolog,
                cells,
                epilog,
            } => {
                self.indent()?;
                self.out.write_str("{}\n")?;
                self.indent += 1;
                self.comment("#", prolog)?;
                for cell in *cells {
                    self.entry_in_dict(cell)?;
                }
                self.indent -= 1;
                self.comment("#", epilog)
            }
        }
    }
    fn entry_in_dict<'a>(&mut self, cell: &Cell<Entry<'a>>) -> Result {
        let entry = cell.get();
        if entry.gap {
            // TODO be strict? f.write_indent(self.indent)?;
            self.out.write_char('\n')?;
        }
        self.comment("//", &entry.before)?;
        match &entry.item {
            Item::Text { value, epilog } => {
                self.indent()?;
                if let Some(only) = entry.key.only_line() {
                    if let Some(text) = Output::one_liner_in_dict(value, only) {
                        self.out.write_str(only)?;
                        self.out.write_char('=')?;
                        self.out.write_str(text)?;
                        self.out.write_char('\n')?;
                    } else {
                        self.out.write_char('<')?;
                        self.out.write_str(only)?;
                        self.out.write_str(">\n")?;
                        self.indent += 1;
                        self.indent()?;
                        self.string(value)?;
                        self.indent -= 1;
                    }
                } else {
                    self.out.write_char('@')?;
                    self.indent += 1;
                    self.string(&entry.key)?;
                    self.indent -= 1;
                    self.indent()?;
                    self.out.write_str("<>\n")?;
                    self.indent += 1;
                    self.indent()?;
                    self.string(value)?;
                    self.indent -= 1;
                }
                self.comment("#", epilog)
            }
            Item::List {
                prolog,
                cells,
                epilog,
            } => {
                self.indent()?;
                if let Some(only) = entry.key.only_line() {
                    self.out.write_char('[')?;
                    self.out.write_str(only)?;
                    self.out.write_str("]\n")?;
                } else {
                    self.out.write_char('@')?;
                    self.indent += 1;
                    self.string(&entry.key)?;
                    self.indent -= 1;
                    self.indent()?;
                    self.out.write_str("[]\n")?;
                }
                self.indent += 1;
                self.comment("#", prolog)?;
                for cell in *cells {
                    self.item_in_list(cell)?;
                }
                self.indent -= 1;
                self.comment("#", epilog)
            }
            Item::Dict {
                prolog,
                cells,
                epilog,
            } => {
                self.indent()?;
                if let Some(only) = entry.key.only_line() {
                    self.out.write_char('{')?;
                    self.out.write_str(only)?;
                    self.out.write_str("}\n")?;
                } else {
                    self.out.write_char('@')?;
                    self.indent += 1;
                    self.string(&entry.key)?;
                    self.indent -= 1;
                    self.indent()?;
                    self.out.write_str("{}\n")?;
                }
                self.indent += 1;
                self.comment("#", prolog)?;
                for cell in *cells {
                    self.entry_in_dict(cell)?;
                }
                self.indent -= 1;
                self.comment("#", epilog)
            }
        }
    }
    fn file<'a>(&mut self, file: &File<'a>) -> Result {
        self.comment("#!", &file.hashbang)?;
        self.comment("#", &file.prolog)?;
        for cell in file.cells {
            self.entry_in_dict(cell)?;
        }
        Ok(())
    }
}
