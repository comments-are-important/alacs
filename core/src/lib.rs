#![no_std]

//! Text in Nested Dictionaries and Lists - with Important Comments

use core::cell::Cell;

#[doc(inline)]
/// build a [walk::Path]
pub use tindalwic_macros::path;

#[doc(inline)]
/// build an [Item] using a subset of the JSON syntax.
///
/// this helps to write code snippets that make a structural change to a [File].
/// a typical snippet would:
///  + [path!].walk([File].cells) to the place to be changed,
///  + use [json!] to build a new [Item],
///  + then use [core::cell::Cell::set] to affect the change.
pub use tindalwic_macros::json;

#[doc(inline)]
pub use tindalwic_macros::arena;

pub mod capped;
pub mod fmt;
pub mod parse;
pub mod walk;

#[cfg(feature = "alloc")]
pub mod alloc;
#[cfg(feature = "bumpalo")]
pub mod bumpalo;

/// the semver plus the git fingerprint
pub const VERSION: &str = env!("TINDALWIC_VERSION");

// ====================================================================================

mod value {
    /// All primitive values in Tindalwic are string slice references, not owned.
    ///
    ///  + [Comment::value](super::Comment::value)
    ///  + [Text::value](super::Item::Text::value)
    ///  + [Entry::key](super::Entry::key)
    ///
    /// They often contain embedded indentation because the parser is zero-copy from
    /// the encoded data. The methods here will strip indentation as necessary.
    /// Apps that modify only a few values do not have to pay for any processing of
    /// unmodified values that are already appropriately indented.
    #[derive(Clone, Copy, Debug)]
    pub struct Value<'a> {
        slice: &'a str,
        indent: usize, // usize::MAX => single line
    }
    impl<'a> PartialEq for Value<'a> {
        fn eq(&self, other: &Self) -> bool {
            if self.indent == other.indent {
                self.slice == other.slice
            } else {
                self.lines().eq(other.lines())
            }
        }
    }
    impl<'a> Value<'a> {
        /// `true` when zero chars (see [str::is_empty]).
        pub fn is_empty(&self) -> bool {
            self.slice.is_empty()
        }
        pub(crate) fn byte_count(&self) -> usize {
            self.slice.as_bytes().len()
        }
        /// `true` if prefix matches (see [str::starts_with]).
        ///
        /// Restricted to char until [core::str::pattern::Pattern] is stable.
        pub fn starts_with(&self, pat: char) -> bool {
            self.slice.starts_with(pat)
        }
        /// the format sometimes allows shorter encoding for single line values
        pub fn only_line(&self) -> Option<&'a str> {
            if self.indent == usize::MAX {
                Some(self.slice)
            } else {
                None
            }
        }
        /// if the value was captured at this indent, then it can be used as is.
        pub fn verbatim(&self, indent: usize) -> Option<&'a str> {
            let only = self.only_line();
            if only.is_some() {
                only
            } else if indent == self.indent {
                Some(self.slice)
            } else {
                None
            }
        }
        /// Returned iterator produces one sub-slice for each line.
        ///
        /// Always produces at least one line. Omits indentation and newline chars.
        pub fn lines(&self) -> impl Iterator<Item = &'a str> {
            // that return type is tricky to satisfy: having two branches here (one
            // optimized for absent indentation) causes E0308 incompatible types:
            //   "distinct uses of `impl Trait` result in different opaque types"
            // attempting to hide them behind closures does not help either:
            //   "no two closures, even if identical, have the same type"
            let d = if self.only_line().is_some() {
                0
            } else {
                self.indent
            };
            self.slice
                .split('\n')
                .enumerate()
                .map(move |(i, s)| if i == 0 || d == 0 { s } else { &s[d..] })
        }
        /// Take as many chars as possible from beginning of slice.
        ///
        /// No indentation is expected at the beginning, subsequent indented lines
        /// (even those with excess indentation) are included.
        pub fn slice_prefix(indent: usize, slice: &'a str) -> Self {
            assert!(indent != usize::MAX, "indent can't be MAX");
            if slice.is_empty() {
                return Value::default();
            }
            let bytes = slice.as_bytes();
            let limit = bytes.len();
            let mut offset = 0usize;
            while bytes[offset] != b'\n' {
                offset += 1;
                if offset >= limit {
                    let indent = usize::MAX;
                    return Value { slice, indent };
                }
            }
            if indent == 0 {
                return Value { slice, indent };
            }
            let mut tabs = crate::parse::indentation(bytes, offset + 1, limit);
            if tabs < indent {
                return Value {
                    slice: &slice[..offset],
                    indent: usize::MAX,
                };
            }
            loop {
                offset += tabs + 1;
                if offset >= limit {
                    return Value { slice, indent };
                }
                while bytes[offset] != b'\n' {
                    offset += 1;
                    if offset >= limit {
                        return Value { slice, indent };
                    }
                }
                tabs = crate::parse::indentation(bytes, offset + 1, limit);
                if tabs < indent {
                    let slice = &slice[..offset];
                    return Value { slice, indent };
                }
            }
        }
    }
    impl<'a> Default for Value<'a> {
        fn default() -> Self {
            Value {
                slice: "",
                indent: usize::MAX,
            }
        }
    }
}
pub use value::Value;
impl<'a> Value<'a> {
    /// linear `O(n)` scan.
    // TODO: add link to `alloc` map view, say it "offers `O(1)`."
    pub fn find_linearly_in(self, cells: Entries<'_>) -> Option<usize> {
        cells.iter().position(|cell| cell.get().key == self)
    }
}
impl<'a> From<&'a str> for Value<'a> {
    fn from(value: &'a str) -> Self {
        Value::slice_prefix(0, value)
    }
}
impl<'a> Eq for Value<'a> {}
impl<'a> core::hash::Hash for Value<'a> {
    fn hash<H: core::hash::Hasher>(&self, state: &mut H) {
        let mut lines = self.lines();
        let first = lines.next().expect("lines is never empty");
        first.hash(state);
        for line in self.lines() {
            b'\n'.hash(state);
            line.hash(state);
        }
    }
}

// ====================================================================================

/// Metadata about an [Item], [Entry] or [File].
///
/// A serialized [Comment] will start with one of three possible markers, depending
/// on its position:
///  + `#!` for [File::hashbang],
///  + `//` for [Entry::before].
///  + `#` for the various `prolog` and `epilog` fields,
///
/// The content is UTF-8 Github Flavored Markdown.
///
/// A field within the [Item] or File will hold the Comment, there is no mechanism to
/// navigate from a Comment to the thing it describes.
///
/// # Examples
///
/// ```
/// # #[cfg(feature="alloc")]
/// # {
/// use tindalwic::*;
/// let comment = Comment {
///     value: "with ~strikethrough~ extension".into(),
/// };
///
/// let html = markdown::to_html_with_options(&comment.value.joined(), &markdown::Options::gfm())
///     .expect(
///         "should never error, according to:
///      <https://docs.rs/markdown/latest/markdown/fn.to_html_with_options.html#errors>",
///     );
///
/// assert_eq!(html, "<p>with <del>strikethrough</del> extension</p>");
/// # }
/// ```
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Comment<'a> {
    /// the string value
    pub value: Value<'a>,
}
impl<'a> Comment<'a> {
    /// helper for setting one of the fields.
    pub fn some(value: &'a str) -> Option<Comment<'a>> {
        Some(Comment {
            value: value.into(),
        })
    }
}

// ------------------------------------------------------------------------------------

/// an association (from key to item) and its metadata.
///
/// at the lowest level, these are stored in an array.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Entry<'a> {
    /// a key can have a blank line before it (before its comment)
    pub gap: bool,
    /// a key can have a comment before it (after its blank line).
    pub before: Option<Comment<'a>>,
    /// the key being associated to an [Item].
    pub key: Value<'a>,
    /// the item associated to the [Entry::key]
    pub item: Item<'a>,
}
impl<'a> Default for Entry<'a> {
    fn default() -> Self {
        Entry {
            gap: false,
            before: None,
            key: Value::default(),
            item: Item::default(),
        }
    }
}
impl<'a> Entry<'a> {
    /// Make a fixed-size array of cells on the stack.
    pub fn array<const N: usize>() -> [Cell<Entry<'a>>; N] {
        ::core::array::from_fn::<_, N, _>(|_| Cell::default())
    }
}

// ------------------------------------------------------------------------------------

/// the slice type for [Item::Dict::cells]
pub type Entries<'a> = &'a [Cell<Entry<'a>>];
/// the slice type for [Item::List::cells]
pub type Items<'a> = &'a [Cell<Item<'a>>];

// ------------------------------------------------------------------------------------

/// the three Item variants
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Item<'a> {
    /// a [Value]
    Text {
        /// the string value
        value: Value<'a>,
        /// A Text can have a Comment after it.
        epilog: Option<Comment<'a>>,
    },
    /// a linear array of [Item]
    List {
        /// A List can have an introductory Comment.
        prolog: Option<Comment<'a>>,
        /// The contents of the Item::List.
        cells: Items<'a>,
        /// A List can have a Comment after it.
        epilog: Option<Comment<'a>>,
    },
    /// an associative array of [Entry]
    Dict {
        /// A Dict can have an introductory Comment.
        prolog: Option<Comment<'a>>,
        /// The contents of the Item::Dict.
        cells: Entries<'a>,
        /// A Dict can have a Comment after it.
        epilog: Option<Comment<'a>>,
    },
}
impl<'a> Default for Item<'a> {
    fn default() -> Self {
        Item::Text {
            value: Value::default(),
            epilog: None,
        }
    }
}
impl<'a> Item<'a> {
    /// Make a fixed-size array of cells on the stack.
    pub fn array<const N: usize>() -> [Cell<Item<'a>>; N] {
        ::core::array::from_fn::<_, N, _>(|_| Cell::default())
    }
    /// wrap a value (no epilog) into an Item::Text
    pub fn text(value: &'a str) -> Self {
        Item::Text {
            value: value.into(),
            epilog: None,
        }
    }
    /// wrap an array of cells of items into an Item::List
    pub fn list(cells: Items<'a>) -> Self {
        Item::List {
            prolog: None,
            cells,
            epilog: None,
        }
    }
    /// wrap an array of cells of entries into an Item::Dict
    pub fn dict(cells: Entries<'a>) -> Self {
        Item::Dict {
            prolog: None,
            cells,
            epilog: None,
        }
    }
}

// ------------------------------------------------------------------------------------

/// the outermost context.
///
/// similar to a [Item::Dict], but with different comments.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct File<'a> {
    /// A File can start with a Unix `#!` Comment.
    pub hashbang: Option<Comment<'a>>,
    /// A File can have an introductory Comment.
    pub prolog: Option<Comment<'a>>,
    /// The contents of the Item::File.
    pub cells: Entries<'a>,
}
impl<'a> File<'a> {
    /// make an [Item::Dict] from self.prolog and self.cells
    pub fn embed_without_hashbang(&self) -> Item<'a> {
        Item::Dict {
            prolog: self.prolog,
            cells: self.cells,
            epilog: None,
        }
    }
    /// take prolog and cells from an [Item::Dict] to make a new File.
    ///
    /// None if the item is not a dictionary.
    pub fn try_from_dict_without_epilog(dict: &Item<'a>) -> Option<Self> {
        match dict {
            Item::Dict { prolog, cells, .. } => Some(File {
                hashbang: None,
                prolog: *prolog,
                cells,
            }),
            _ => None,
        }
    }
}

// ====================================================================================
