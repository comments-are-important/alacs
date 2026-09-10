use tindalwic::{arena, parse::Parse as _};
fn main() {
    let mut encoded = String::from("key=value");
    arena! { let mut arena = <1dict>; }
    let file = arena.panic_first_error(&encoded);
    encoded.clear();
    assert!(file.hashbang.is_none());
}
