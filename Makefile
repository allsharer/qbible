# qbible — common development tasks. Run 'make help'.
PYTHON ?= python3
VERSION := $(shell sed -n 's/^__version__ = "\(.*\)"/\1/p' qbible/__init__.py)
PACK := build/translations/kjv.sqlite

.PHONY: help data test test-python test-browser check run serve deb test-deb install-user uninstall-user release clean

help:
	@echo "make data            build and validate the KJV translation pack ($(PACK))"
	@echo "make test            run all automated tests (Python + browser)"
	@echo "make test-python     Python tests only"
	@echo "make test-browser    browser tests only (needs npm install + Chrome)"
	@echo "make serve           start the browser interface from the source tree"
	@echo "make deb             build dist/qbible_$(VERSION)_all.deb"
	@echo "make test-deb        check the built .deb (lintian + run extracted copy)"
	@echo "make install-user    install to ~/.local (no root)"
	@echo "make uninstall-user  remove the ~/.local installation (keeps user data)"
	@echo "make release         data + tests + deb + checks + source tarball"
	@echo "make clean           remove build outputs"

$(PACK): data/sources/eng-kjv_vpl.zip data/sources/SOURCES.json qbible/importer.py qbible/schema.py
	$(PYTHON) -m qbible.build_data

data:
	$(PYTHON) -m qbible.build_data

test: test-python test-browser

test-python: $(PACK)
	$(PYTHON) -m unittest discover -s tests -t . -v

node_modules/puppeteer-core:
	npm install --no-audit --no-fund

test-browser: $(PACK) node_modules/puppeteer-core
	npm run --silent test:browser

serve: $(PACK)
	./bin/qbible serve --open

deb: $(PACK)
	scripts/build-deb.sh

test-deb: deb
	scripts/test-deb.sh dist/qbible_$(VERSION)_all.deb

install-user: $(PACK)
	scripts/install.sh

uninstall-user:
	scripts/uninstall.sh

release:
	scripts/release.sh

clean:
	rm -rf build dist
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
