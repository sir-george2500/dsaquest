# Convenience targets. The application itself installs with uv/pip; these cover
# the pieces a Python package installer does not handle.

PREFIX ?= $(HOME)/.local
MANDIR ?= $(PREFIX)/share/man
VENV   ?= .venv

.PHONY: help install-man uninstall-man lint test test-fast check

help:
	@echo "make install-man    install dsa(1) and dsa-quest(7) into $(MANDIR)"
	@echo "make uninstall-man  remove them again"
	@echo "make test           full test suite (compiles C++, takes minutes)"
	@echo "make test-fast      skip the tests that compile C++"
	@echo "make lint           ruff check and format check"
	@echo "make check          lint + full test suite"

install-man:
	@install -d $(MANDIR)/man1 $(MANDIR)/man7
	@install -m 644 docs/man/dsa.1 $(MANDIR)/man1/dsa.1
	@install -m 644 docs/man/dsa-quest.7 $(MANDIR)/man7/dsa-quest.7
	@# Index it. mandoc and man-db use different databases; run whichever exists.
	@# Without an index, "dsa" resolves to OpenSSL's dsa(1ssl) instead of ours.
	@command -v makewhatis >/dev/null 2>&1 && makewhatis $(MANDIR) 2>/dev/null || true
	@command -v mandb      >/dev/null 2>&1 && mandb -q $(MANDIR) 2>/dev/null || true
	@echo "installed to $(MANDIR)"
	@echo
	@echo "$(MANDIR) is not on the default MANPATH. Add to your shell profile:"
	@echo "    export MANPATH=\"$(MANDIR):\$$MANPATH\""
	@echo
	@echo "then:  man dsa    and    man 7 dsa-quest"

uninstall-man:
	@rm -f $(MANDIR)/man1/dsa.1 $(MANDIR)/man7/dsa-quest.7
	@command -v makewhatis >/dev/null 2>&1 && makewhatis $(MANDIR) 2>/dev/null || true
	@echo "removed from $(MANDIR)"

lint:
	$(VENV)/bin/python -m ruff check src/ tests/
	$(VENV)/bin/python -m ruff format --check src/ tests/
	@mandoc -T lint docs/man/dsa.1 docs/man/dsa-quest.7 2>&1 | grep -v STYLE || true

test:
	$(VENV)/bin/python -m pytest -q

test-fast:
	$(VENV)/bin/python -m pytest -q -m "not slow"

check: lint test
