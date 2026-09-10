use bumpalo::Bump;
use serde::Serialize;
use serde::de::DeserializeSeed;
use tindalwic::File;
use tindalwic::bumpalo::Arena;
use tindalwic_serde::{Compact, Neutered, Verbose};
use wasm_bindgen::prelude::*;

#[wasm_bindgen(start)]
fn initialize() {
    console_error_panic_hook::set_once();
}

#[wasm_bindgen]
pub fn version() -> String {
    tindalwic::VERSION.to_string()
}

fn into_json<T: ?Sized + Serialize>(value: &T) -> Result<String, String> {
    serde_json::to_string_pretty(value).map_err(|e| e.to_string())
}
fn into_toml<T: ?Sized + Serialize>(value: &T) -> Result<String, String> {
    toml_edit::ser::to_string_pretty(value).map_err(|e| e.to_string())
}
fn into_yaml<T: ?Sized + Serialize>(value: &T) -> Result<String, String> {
    yaml_serde::to_string(value).map_err(|e| e.to_string())
}

#[wasm_bindgen]
pub fn from_tindalwic(
    input: String,  // the tindalwic data
    mode: String,   // Neutered | Compact | Verbose
    format: String, // JSON | TOML | YAML
) -> Result<String, String> {
    let bump = Bump::new();
    let mut arena = Arena::new(&bump);
    let file = arena.format_errors("", &input, usize::MAX)?;
    match (&mode[..], &format[..]) {
        ("Neutered", "JSON") => into_json(&Neutered(file)),
        ("Neutered", "TOML") => into_toml(&Neutered(file)),
        ("Neutered", "YAML") => into_yaml(&Neutered(file)),
        ("Compact", "JSON") => into_json(&Compact(file)),
        ("Compact", "TOML") => into_toml(&Compact(file)),
        ("Compact", "YAML") => into_yaml(&Compact(file)),
        ("Verbose", "JSON") => into_json(&Verbose(file)),
        ("Verbose", "TOML") => into_toml(&Verbose(file)),
        ("Verbose", "YAML") => into_yaml(&Verbose(file)),
        _ => Err("bad parameters".to_string()),
    }
}

fn from_json<'de, 'a>(
    input: &'de str,
    seed: impl DeserializeSeed<'de, Value = File<'a>>,
) -> Result<File<'a>, String> {
    let mut de = serde_json::Deserializer::from_str(input);
    seed.deserialize(&mut de).map_err(|e| e.to_string())
}
fn from_toml<'de, 'a>(
    input: &'de str,
    seed: impl DeserializeSeed<'de, Value = File<'a>>,
) -> Result<File<'a>, String> {
    let de = toml_edit::de::Deserializer::parse(input).map_err(|e| e.to_string())?;
    seed.deserialize(de).map_err(|e| e.to_string())
}
fn from_yaml<'de, 'a>(
    input: &'de str,
    seed: impl DeserializeSeed<'de, Value = File<'a>>,
) -> Result<File<'a>, String> {
    let de = yaml_serde::Deserializer::from_str(input);
    seed.deserialize(de).map_err(|e| e.to_string())
}

#[wasm_bindgen]
pub fn into_tindalwic(
    input: String,  // the data in their format
    mode: String,   // Neutered | Compact | Verbose
    format: String, // JSON | TOML | YAML
) -> Result<String, String> {
    let bump = Bump::new();
    let mut arena = Arena::new(&bump);
    match (&mode[..], &format[..]) {
        ("Neutered", "JSON") => from_json(&input, Neutered::seed(&mut arena)),
        ("Neutered", "TOML") => from_toml(&input, Neutered::seed(&mut arena)),
        ("Neutered", "YAML") => from_yaml(&input, Neutered::seed(&mut arena)),
        ("Compact", "JSON") => from_json(&input, Compact::seed(&mut arena)),
        ("Compact", "TOML") => from_toml(&input, Compact::seed(&mut arena)),
        ("Compact", "YAML") => from_yaml(&input, Compact::seed(&mut arena)),
        ("Verbose", "JSON") => from_json(&input, Verbose::seed(&mut arena)),
        ("Verbose", "TOML") => from_toml(&input, Verbose::seed(&mut arena)),
        ("Verbose", "YAML") => from_yaml(&input, Verbose::seed(&mut arena)),
        _ => Err("bad parameters".to_string()),
    }
    .map(|f| f.to_string())
}
