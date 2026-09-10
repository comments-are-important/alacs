//! generate random files, run them through the library algorithms.
//! the randomness is not attempting to produce data that mimics the real world in any
//! way. other benchmarks do that. instead, the ratios here are chosen to even out the
//! library profiling line hit counts that would happen during this test: all the
//! branches coming from each decision point in the algorithms should be taken roughly
//! the same number of times.

#![allow(missing_docs)]

use bumpalo::Bump;
use rand::prelude::IndexedRandom;
use rand::rngs::SmallRng;
use rand::{Rng, RngExt, SeedableRng};
use std::fmt::{self, Write};
use tindalwic::bumpalo::Arena;
use tindalwic::parse::{Parse, ParseError};
use tindalwic::{Comment, Entry, File, Item};

/// a very blurry outline of some data. created first to be able to call the
/// Arena API in the order it requires.
#[derive(Debug)]
struct Silhouette {
    branches: usize, // recursive count excluding leaf nodes but including self
    children: Vec<Option<Silhouette>>, // None indicates position of a leaf
}
impl Silhouette {
    fn new() -> Self {
        Silhouette {
            branches: 1,
            children: Vec::new(),
        }
    }
    fn grow(&mut self, mut at: usize, leaf: bool) {
        // the `at` corresponds to index within post-order traversal (ignore leaf nodes)
        if at >= self.branches {
            panic!("can't grow at {at} - no such branch exists");
        }
        for kid in &mut self.children {
            let Some(kid) = kid else { continue };
            if at < kid.branches {
                kid.grow(at, leaf);
                if !leaf {
                    self.branches += 1;
                }
                return;
            }
            at -= kid.branches;
        }
        if at != 0 {
            panic!("bad math somewhere");
        }
        if leaf {
            self.children.push(None);
        } else {
            self.children.push(Some(Silhouette::new()));
            self.branches += 1;
        }
    }
    fn random<R: Rng + ?Sized>(size: usize, rng: &mut R) -> Self {
        let mut root = Silhouette::new();
        for _ in 1..size {
            let at = rng.random_range(..root.branches);
            let leaf = rng.random_ratio(1, 3);
            root.grow(at, leaf);
            // println!("grow({at},{leaf}) -> {root}");
        }
        root
    }
}
impl fmt::Display for Silhouette {
    fn fmt(&self, out: &mut fmt::Formatter<'_>) -> fmt::Result {
        out.write_char('(')?;
        usize::fmt(&self.branches, out)?;
        for kid in &self.children {
            if let Some(kid) = kid {
                Silhouette::fmt(kid, out)?;
            } else {
                out.write_char('.')?;
            }
        }
        out.write_char(')')?;
        Ok(())
    }
}

/// generate random files containing the requested number of items.
pub struct Random<'a, 'r, R: Rng + ?Sized> {
    bump: &'a Bump,
    arena: &'r mut Arena<'a>,
    rng: &'r mut R,
    sample: Vec<char>,
}
impl<'a, 'r, R: Rng + ?Sized> Random<'a, 'r, R> {
    fn value(&mut self) -> &'a str {
        let mut value = String::new();
        let newline = self.rng.random_bool(0.5);
        let lines = if !newline {
            1
        } else {
            self.rng.random_range(1..=4)
        };
        for line in 0..lines {
            if line != 0 {
                value.push('\n');
            }
            let mut len: usize = self.rng.random_range(..5);
            while len > 0 {
                let c: char = if self.sample.is_empty() {
                    self.rng.random()
                } else {
                    *self.sample.choose(&mut self.rng).unwrap()
                };
                if c != '\n' {
                    value.push(c);
                    len -= 1;
                }
            }
        }
        self.bump.alloc_str(&value)
    }
    fn comment(&mut self) -> Option<Comment<'a>> {
        if self.rng.random_bool(0.5) {
            Some(Comment {
                value: self.value().into(),
            })
        } else {
            None
        }
    }
    fn item(&mut self, shape: &Option<Silhouette>) -> Result<Item<'a>, ParseError> {
        Ok(if let Some(parent) = shape {
            if self.rng.random_ratio(1, 2) {
                self.dict(parent)?
            } else {
                self.list(parent)?
            }
        } else {
            Item::text(self.value())
        })
    }
    fn list(&mut self, shape: &Silhouette) -> Result<Item<'a>, ParseError> {
        for kid in &shape.children {
            let item = self.item(kid)?;
            self.arena
                .builder()
                .push_item(item)
                .map_err(ParseError::Memory)?;
        }
        Ok(Item::List {
            prolog: self.comment(),
            cells: self
                .arena
                .builder()
                .finish_items(shape.children.len())
                .map_err(ParseError::Memory)?,
            epilog: self.comment(),
        })
    }
    fn dict(&mut self, shape: &Silhouette) -> Result<Item<'a>, ParseError> {
        for kid in &shape.children {
            let before = self.comment();
            let key = self.value().into();
            let item = self.item(kid)?;
            self.arena
                .builder()
                .push_entry(Entry {
                    gap: self.rng.random_bool(0.2),
                    before,
                    key,
                    item,
                })
                .map_err(ParseError::Memory)?;
        }
        Ok(Item::Dict {
            prolog: self.comment(),
            cells: self
                .arena
                .builder()
                .finish_entries(shape.children.len())
                .map_err(ParseError::Memory)?,
            epilog: self.comment(),
        })
    }
    pub fn file(&mut self, size: usize) -> File<'a> {
        let shape = Silhouette::random(size, self.rng);
        let dict = self.dict(&shape).unwrap();
        File::try_from_dict_without_epilog(&dict).unwrap()
    }
}

#[test]
fn several() {
    let seed: u64 = rand::rng().random();
    println!("seed={seed}");
    let mut rng = SmallRng::seed_from_u64(seed);
    for _loop in 0..5000 {
        let bump = Bump::new();
        let mut arena = Arena::new(&bump);
        let mut random = Random {
            bump: &bump,
            arena: &mut arena,
            rng: &mut rng,
            sample: Vec::new(), //"ABCDEFGHIJKLMNOPQRSTUVWXYZ".chars().collect(),
        };
        let original: File = random.file(32);
        let encoded = original.to_string();
        assert_eq!(original, arena.panic_first_error(&encoded));
    }
}
