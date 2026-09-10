//! supporting code for the path! macro.
//! everything here must be pub so macro can use it,
//! but using these directly is not recommended.
//! using path! is much easier.

use crate::{Entry, Item, Value};
use core::cell::Cell;

/// a decision along a walk.
#[derive(Debug)]
pub enum Branch<'p> {
    /// select list item by index
    Item(usize),
    /// select dict entry by key
    Entry(Value<'p>),
    /// end at text
    Text,
    /// end at list
    List,
    /// end at dict
    Dict,
}
/// information about where a walk went wrong.
#[derive(Debug)]
pub struct PathError<'p> {
    /// zero or more good steps and one last bad step
    pub failed: &'p [Branch<'p>],
    /// English description of the problem
    pub message: &'static str,
}
impl<'p> core::error::Error for PathError<'p> {}

/// a sequence of Branch built and used by the walk macro.
///
/// the ENTRY parameter determines the Cell inner type of `Ok` walk:
///  + false => Item (so penultimate branch must be a Branch::Item)
///  + true => Entry (so penultimate branch must be a Branch::Entry)
#[derive(Debug)]
pub struct Path<'p, const ENTRY: bool> {
    /// all the decisions for a walk
    branches: &'p [Branch<'p>],
}
impl<'p, const ENTRY: bool> Path<'p, ENTRY> {
    /// construct an error indicating the given path step failed
    fn error_at(&self, bad: usize, message: &'static str) -> PathError<'p> {
        PathError {
            failed: &self.branches[..=bad],
            message,
        }
    }
}
impl<'p> Path<'p, false> {
    /// construct a path expected to end at an item in a list
    pub fn new(branches: &'p [Branch<'p>]) -> Self {
        let mut rev = branches.iter().rev();
        match rev.next() {
            Some(Branch::Text) | Some(Branch::List) | Some(Branch::Dict) => (),
            _ => panic!("path must end with: Text|List|Dict"),
        }
        match rev.next() {
            Some(Branch::Item(_)) => (),
            _ => panic!("path must end within an item in a list"),
        }
        while let Some(branch) = rev.next() {
            match branch {
                Branch::Item(_) | Branch::Entry(_) => (),
                _ => panic!("Text|List|Dict can only be at end of path"),
            }
        }
        Path { branches }
    }
    /// walk down a path that ends at an item in a list
    pub fn walk<'a>(&self, mut item: Item<'a>) -> Result<&'a Cell<Item<'a>>, PathError<'p>> {
        let mut cell: Option<&'a Cell<Item<'a>>> = None;
        for (step, branch) in self.branches.iter().enumerate() {
            match (branch, item) {
                (Branch::Item(at), Item::List { cells, .. }) => {
                    let Some(found) = cells.get(*at) else {
                        return Err(self.error_at(step, "index out of bounds"));
                    };
                    cell = Some(found);
                    item = found.get();
                }
                (Branch::Entry(key), Item::Dict { cells, .. }) => {
                    let Some(found) = key.find_linearly_in(cells) else {
                        return Err(self.error_at(step, "key not found"));
                    };
                    cell = None;
                    item = cells[found].get().item;
                }
                (Branch::Text, Item::Text { .. })
                | (Branch::List, Item::List { .. })
                | (Branch::Dict, Item::Dict { .. }) => {
                    // the else branch might be impossible (because error already happened)
                    // avoid using .ok_or_else so the closure is not an uncovered fn...
                    return if let Some(found) = cell {
                        Ok(found)
                    } else {
                        Err(self.error_at(
                            self.branches.len() - 1,
                            "path did not end at an item inside a list",
                        ))
                    };
                }
                _ => return Err(self.error_at(step, "wrong type of item")),
            }
        }
        panic!("impossible because of checks in Path::new");
    }
}
impl<'p> Path<'p, true> {
    /// construct a path expected to end at an entry in a dict
    pub fn new(branches: &'p [Branch<'p>]) -> Self {
        let mut rev = branches.iter().rev();
        match rev.next() {
            Some(Branch::Text) | Some(Branch::List) | Some(Branch::Dict) => (),
            _ => panic!("path must end with: Text|List|Dict"),
        }
        match rev.next() {
            Some(Branch::Entry(_)) => (),
            _ => panic!("path must end within an entry in a dict"),
        }
        while let Some(branch) = rev.next() {
            match branch {
                Branch::Item(_) | Branch::Entry(_) => (),
                _ => panic!("Text|List|Dict can only be at end of path"),
            }
        }
        Path { branches }
    }
    /// walk down a path that ends at an item in a dict
    pub fn walk<'a>(&self, mut item: Item<'a>) -> Result<&'a Cell<Entry<'a>>, PathError<'p>> {
        let mut cell: Option<&'a Cell<Entry<'a>>> = None;
        for (step, branch) in self.branches.iter().enumerate() {
            match (branch, item) {
                (Branch::Item(at), Item::List { cells, .. }) => {
                    let Some(found) = cells.get(*at) else {
                        return Err(self.error_at(step, "index out of bounds"));
                    };
                    cell = None;
                    item = found.get();
                }
                (Branch::Entry(key), Item::Dict { cells, .. }) => {
                    let Some(found) = key.find_linearly_in(cells) else {
                        return Err(self.error_at(step, "key not found"));
                    };
                    let found = &cells[found];
                    cell = Some(found);
                    item = found.get().item;
                }
                (Branch::Text, Item::Text { .. })
                | (Branch::List, Item::List { .. })
                | (Branch::Dict, Item::Dict { .. }) => {
                    // the else branch might be impossible (because error already happened)
                    // avoid using .ok_or_else so the closure is not an uncovered fn...
                    return if let Some(found) = cell {
                        Ok(found)
                    } else {
                        Err(self.error_at(
                            self.branches.len() - 1,
                            "path did not end at an item inside a list",
                        ))
                    };
                }
                _ => return Err(self.error_at(step, "wrong type of item")),
            }
        }
        panic!("impossible because of checks in Path::new");
    }
}
