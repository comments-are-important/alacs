
set shell := ["bash", "-uc"]

all: fmt (test "-q") playground coverage doc api lines msrv

@_is_running_outside_devcontainer:
    [[ ! ( -e /tmp/.devcontainerId \
           || -v TINDALWIC_CID ) ]]

@_is_running_inside_devcontainer:
    [[ -e /tmp/.devcontainerId \
       && -v TINDALWIC_CID \
       && "$(< /tmp/.devcontainerId)" == "$TINDALWIC_CID" ]]

@_install crate: _is_running_inside_devcontainer
    cargo install --list \
      | grep -q {{ crate }} \
      || cargo binstall --no-confirm --only-signed --disable-telemetry {{ crate }}

@_install_version crate version: _is_running_inside_devcontainer
    cargo install --list \
      | grep -q "^{{ crate }} v{{ version }}:$" \
      || cargo binstall --no-confirm --only-signed --disable-telemetry {{ crate }} --version {{ version }}

# -----------------------------------------------------------------------------

quiet := '(^| )(-q|--quiet)( |$)'
color := '(\x1b\[[0-9;]*[mK])*'

test *OPTS: _is_running_inside_devcontainer
    cargo test -p tindalwic --test unit {{OPTS}}
    cargo test -p tindalwic --test unit --features alloc {{OPTS}}
    cargo test -p tindalwic --test unit --features bumpalo {{OPTS}}
    cargo test -p tindalwic --test unit --all-features {{OPTS}}
    cargo test -p tindalwic --test rand --all-features {{OPTS}}
    cargo test -p tindalwic --doc --all-features {{OPTS}}
    cargo test -p tindalwic --test trybuild --all-features {{OPTS}} \
      {{ if OPTS =~ quiet { '2> >(grep --line-buffered -P "^'+color+'test '+color+'tests/trybuild/.*[^o][^k]$")' } else {''} }}
    cargo test -p tindalwic-serde --test serde {{OPTS}}

coverage: _is_running_inside_devcontainer (_install "cargo-llvm-cov")
    yes | LLVM_COV_FLAGS="--show-expansions --show-instantiations" \
      cargo +nightly llvm-cov --html --branch -p tindalwic --test unit --all-features --show-missing-lines

doc: _is_running_inside_devcontainer
    cargo doc --all-features --no-deps --document-private-items

fmt: _is_running_inside_devcontainer
    cargo +nightly fmt

msrv: _is_running_inside_devcontainer (_install "cargo-msrv")
    #!/usr/bin/env bash
    for path in $(cargo metadata --no-deps --format-version 1 | jq -r '.packages[].manifest_path')
    do
      cargo msrv verify --path "$(dirname $path)"
    done

playground: _is_running_inside_devcontainer (_install "wasm-opt")
    cargo build -p tindalwic-playground --target wasm32-unknown-unknown --profile dev
    cargo build -p tindalwic-playground --target wasm32-unknown-unknown --profile release-small
    just _install_version wasm-bindgen-cli "$(cargo pkgid -p wasm-bindgen | sed -E -e 's=^[^@]+@([0-9.]+).*$=\1=')"
    wasm-bindgen --target web --keep-debug \
      --out-dir target/playground-dev \
      target/wasm32-unknown-unknown/debug/tindalwic_playground.wasm
    wasm-bindgen --target web --no-typescript --remove-name-section --remove-producers-section \
      --out-dir target/playground-release \
      target/wasm32-unknown-unknown/release-small/tindalwic_playground.wasm
    cp playground/favicon.ico target/
    cp playground/{index.html,favicon.ico} target/playground-dev/
    cp playground/{index.html,favicon.ico} target/playground-release/
    cd target/playground-release ; wasm-opt -Oz --enable-bulk-memory \
      -o tindalwic_playground_bg.wasm tindalwic_playground_bg.wasm

api: _is_running_inside_devcontainer (_install "cargo-public-api")
    mkdir -p target/public-api/{all,default}
    cargo public-api -p tindalwic --target-dir target/public-api/default \
      >target/public-api/tindalwic-default.api
    cargo public-api -p tindalwic --all-features --target-dir target/public-api/all \
      >target/public-api/tindalwic-all.api
    cat target/public-api/tindalwic-all.api \
      | sed -E -e 's=^impl (.*)=|\1|impl|=' \
      | sed -E -e 's=^(impl<[^>]+>) (.*)=|\2|\1|=' \
      | sed -E -e 's=^pub (enum|fn|const fn|mod|struct|use|type) (&?)(.*)=|\3|\2\1|=' \
      | sed -E -e 's=^pub (.*)=|\1|property|=' \
      | LC_ALL=C sort -u >target/public-api/tindalwic-all.org

lines: _is_running_inside_devcontainer (_install "cargo-llvm-lines")
    cargo llvm-lines -p tindalwic --all-features >target/llvm-lines.out

# -----------------------------------------------------------------------------

sitter:
  #!/usr/bin/env bash
  set -xe
  cd grammar
  npx tree-sitter --version || npm ci
  npx tree-sitter generate
  npx tree-sitter build -o ../target/tree-sitter-tindalwic.so
  npx tree-sitter build --wasm -o ../target/tree-sitter-tindalwic.wasm

# -----------------------------------------------------------------------------

setup: _is_running_outside_devcontainer
    code --install-extension ms-vscode-remote.remote-containers

down: _is_running_outside_devcontainer
    docker rm -f tindalwic-devcontainer-vscode
    docker image rm $(docker image ls -q --filter "reference=vsc-tindalwic-*")

httpd: _is_running_outside_devcontainer
    cd target ; python -m http.server >&http.server.log

links: _is_running_outside_devcontainer
    #!/usr/bin/env bash
    set -x
    PROJECT='https://raw.githubusercontent.com/comments-are-important/tindalwic'
    COMMIT="$(git rev-parse HEAD)"
    if git merge-base --is-ancestor "$COMMIT" origin/main
    then
      git log -1
      echo ''
      git ls-tree -r --format "$PROJECT/$COMMIT/%(path)" HEAD
    else
      echo "HEAD is not known to be in origin/main... push (maybe fetch too)"
    fi
