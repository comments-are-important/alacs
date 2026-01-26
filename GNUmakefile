.ONESHELL:
SHELL = bash

usage: ;@
	if which -s less grep
	then
	  grep --color=always -E '|^#.*|`[^`]*`' README.md | less -R --use-color
	elif which -s pager
	then
	  pager README.md
	else
	  more README.md
	fi
.PHONY: usage

must-run-outside: ;@
	if [[ -n "$$ALACS_DCID" && "$$(< /tmp/.devcontainerId)" == "ALACS=$$ALACS_DCID" ]]
	then
	  echo 'must run outside devcontainer'
	  exit 1
	fi
.PHONY: must-run-outside

must-run-inside: ;@
	if [[ -z "$$ALACS_DCID" || "$$(< /tmp/.devcontainerId)" != "ALACS=$$ALACS_DCID" ]]
	then
	  echo 'must run inside devcontainer'
	  exit 1
	fi
.PHONY: must-run-inside

# =====================================================================================

setup: must-run-outside ;@
	code --install-extension ms-vscode-remote.remote-containers \
	  | sed -e 's= is already installed[.].*= is already installed.='
.PHONY: setup

down: must-run-outside ;@
	docker rm -f ALACS-devcontainer-vscode
.PHONY: down

# =====================================================================================

python/test: must-run-inside
	uv run --dev -- python -m alacs_test
.PHONY: python/test

python/repl: must-run-inside
	uv run --dev -- python -i -c "import alacs_test;from alacs import *"
.PHONY: python/repl

python/profile: must-run-inside
	mkdir -p /tmp/alacs_test
	cd /tmp/alacs_test
	uv run --dev -- python -m cProfile -o .pstats -m alacs_test
	uv run --dev -- snakeviz .pstats
.PHONY: python/profile

python/coverage: must-run-inside
	mkdir -p /tmp/alacs_test
	cd /tmp/alacs_test
	uv run --dev -- coverage run --branch --source=alacs -m alacs_test
	uv run --dev -- coverage html --directory=.
	uv run --dev -- python -m http.server
.PHONY: python/coverage

# =====================================================================================
