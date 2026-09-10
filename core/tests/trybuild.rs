#![allow(missing_docs)]

#[test]
fn expected_compilation_failures() {
    trybuild::TestCases::new().compile_fail("tests/trybuild/*.rs");
}

extern crate tindalwic as renamed;
use renamed::json;

#[test]
fn dollar_crate() {
    json! {
        $crate = renamed;
        let entries = {}.unwrap();
        completed.unwrap();
    }
    assert!(entries.is_empty());
}
