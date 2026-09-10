#![allow(missing_docs)]

use std::{env, fs, process::Command};

fn scrub(bytes: Vec<u8>) -> String {
    String::from(String::from_utf8_lossy(&bytes).trim())
}

fn git(args: &[&str]) -> String {
    let output = Command::new("git")
        .args(args)
        .env("LC_ALL", "C")
        .env("GIT_CONFIG_NOSYSTEM", "1")
        .env("GIT_OPTIONAL_LOCKS", "0")
        .output()
        .unwrap();
    if !output.status.success() {
        panic!("git {} exit: {}", args[0], output.status)
    } else if !output.stderr.is_empty() {
        panic!("git {} stderr: {}", args[0], scrub(output.stderr))
    }
    scrub(output.stdout)
}

fn require_git(args: &[&str]) -> String {
    let stdout = git(args);
    if stdout.is_empty() {
        panic!("git {} produced no output", args[0])
    }
    stdout
}

fn main() {
    let version = env::var("CARGO_PKG_VERSION").expect("missing CARGO_PKG_VERSION");
    let sha1 = if let Ok(json) = fs::read_to_string(".cargo_vcs_info.json") {
        let Some((_, after)) = json.split_once(r#""sha1": ""#) else {
            panic!("sha1 absent from .cargo_vcs_info.json")
        };
        let end = after
            .find('"')
            .expect("sha1 not terminated in .cargo_vcs_info.json");
        after[..end].to_string()
    } else if matches!(fs::exists("../.git"), Ok(true)) {
        println!("cargo::rerun-if-changed=src");
        println!(
            "cargo::rerun-if-changed={}",
            require_git(&["rev-parse", "--git-path", "logs/HEAD"])
        );
        if git(&["status", "--porcelain"]).is_empty() {
            // not dirty so commit sha1 is accurate
            require_git(&["rev-parse", "HEAD"])
        } else {
            // in dev cycle (can't panic) no sha1 anywhere
            "uncommitted".to_string()
        }
    } else {
        panic!("unable to determine git sha1 for TINDALWIC_VERSION")
    };
    println!("cargo::rustc-env=TINDALWIC_VERSION={version} ({sha1})");
}
