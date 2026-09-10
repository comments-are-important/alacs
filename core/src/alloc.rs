//! all this stuff is enabled by the "alloc" feature.

extern crate alloc;

use crate::Value;
use alloc::string::String;

impl<'a> Value<'a> {
    /// Allocates a [String], filled with the UTF-8 copied from `self`.
    pub fn joined(&self) -> String {
        if let Some(slice) = self.verbatim(0) {
            String::from(slice)
        } else {
            let mut result = String::with_capacity(self.byte_count());
            let mut iter = self.lines();
            if let Some(first) = iter.next() {
                result.push_str(first)
            }
            for more in iter {
                result.push('\n');
                result.push_str(more);
            }
            result
        }
    }
}

/// turn a formatted Rust source code string literal into tindalwic.
pub fn from_literal(literal: &'static str) -> String {
    let mut lines = literal.lines().enumerate();
    let Some((_, line)) = lines.next() else {
        return String::from("");
    };
    assert!(line.is_empty(), "start on 2nd line");
    let Some((_, line)) = lines.next() else {
        return String::from("");
    };
    let mut result = String::from(line.trim_start());
    let prefix = &line[0..line.len() - result.len()];
    let mut more = lines.next();
    while let Some((_, line)) = more {
        let Some(mut remainder) = line.strip_prefix(prefix) else {
            break;
        };
        result.push('\n');
        while let Some(trailing) = remainder.strip_prefix("    ") {
            result.push('\t');
            remainder = trailing;
        }
        result.push_str(remainder);
        more = lines.next()
    }
    if let Some((num, line)) = more {
        assert!(lines.next().is_none(), "line {num} isn't indented");
        assert!(line.trim().is_empty(), "last line isn't blank");
    }
    result.push('\n');
    result
}
