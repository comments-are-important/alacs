//! all this stuff is enabled by the "bumpalo" feature.

extern crate alloc;

use crate::parse::{Build, Parse, ParseError, Reported};
use crate::{Entries, Entry, File, Item, Items};
use alloc::string::String;
use alloc::vec::Vec;
use bumpalo::Bump;
use core::cell::Cell;
use core::fmt::Write;
use core::writeln;

/// this pattern is typically implemented atop RefCell, but because this is in a
/// critical path, small unsafe blocks avoid the cost of those runtime checks.
struct CellVec<T>(Cell<Vec<T>>);
impl<T: Copy> CellVec<T> {
    fn new() -> Self {
        CellVec(Cell::new(Vec::new()))
    }
    fn push(&self, value: T) -> Option<()> {
        let CellVec(cell) = self;
        // SAFETY: Cell instance is private, no ref to its Vec value leaks outside this
        // impl, except via this let, only as receiver in Vec methods, which are safe.
        let vec = unsafe { &mut *cell.as_ptr() };
        vec.push(value);
        Some(())
    }
    fn finish<'b>(&self, count: usize, bump: &'b Bump) -> Option<&'b [Cell<T>]> {
        let CellVec(cell) = self;
        // SAFETY: Cell instance is private, no ref to its Vec value leaks outside this
        // impl, except via this let, only as receiver in Vec methods, which are safe.
        let vec = unsafe { &mut *cell.as_ptr() };
        let start = vec.len().checked_sub(count)?;
        let cells = bump.alloc_slice_fill_with(count, |i| Cell::new(vec[start + i]));
        vec.truncate(start);
        Some(cells)
    }
}

struct HeapBuilder<'a> {
    items: CellVec<Item<'a>>,
    entries: CellVec<Entry<'a>>,
    bump: &'a Bump,
}
impl<'a> Build<'a> for HeapBuilder<'a> {
    fn finish_items(&mut self, count: usize) -> Result<Items<'a>, &'static str> {
        self.items
            .finish(count, self.bump)
            .ok_or("not enough items to make that list")
    }
    fn finish_entries(&mut self, count: usize) -> Result<Entries<'a>, &'static str> {
        self.entries
            .finish(count, self.bump)
            .ok_or("not enough entries to make that dict")
    }
    fn push_item(&mut self, item: Item<'a>) -> Result<(), &'static str> {
        self.items.push(item).ok_or("no room for item")
    }
    fn push_entry(&mut self, entry: Entry<'a>) -> Result<(), &'static str> {
        self.entries.push(entry).ok_or("no room for entry")
    }
    fn intern(&mut self, value: &'_ str) -> Result<&'a str, &'static str> {
        Ok(self.bump.alloc_str(value))
    }
}

/// a flavor of Arena that uses bumpalo to put things in the heap.
pub struct Arena<'a> {
    builder: HeapBuilder<'a>,
}
impl<'a> Parse<'a> for Arena<'a> {
    fn builder(&mut self) -> &mut dyn Build<'a> {
        &mut self.builder
    }
}
impl<'a> Arena<'a> {
    /// the Bump needs an outside let binding so it lives long enough.
    pub fn new(bump: &'a Bump) -> Self {
        let builder = HeapBuilder {
            items: CellVec::new(),
            entries: CellVec::new(),
            bump,
        };
        Arena { builder }
    }
    /// call the parser on the provided content, collect first `count` errors.
    pub fn collect_errors(
        &mut self,
        content: &'a str,
        count: usize,
    ) -> Result<File<'a>, Vec<ParseError>>
    where
        Self: Sized,
    {
        let mut errors = Vec::new();
        self.report_errors(content, &mut |err| {
            if errors.len() >= count {
                return Reported::Abort;
            }
            errors.push(err);
            Reported::Continue
        })
        .ok_or_else(|| errors)
    }
    /// call the parser on the provided content, describe any errors using GCC format.
    pub fn format_errors(
        &mut self,
        path: &str,
        content: &'a str,
        count: usize,
    ) -> Result<File<'a>, String> {
        self.collect_errors(content, count).map_err(|mut errors| {
            if errors.is_empty() {
                errors.push(ParseError::at(0, "an unknown error occurred"));
            }
            let mut out = String::new();
            for error in errors {
                writeln!(out, "{path}:{error}").expect("write! failed");
            }
            out
        })
    }
}
