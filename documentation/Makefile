SPHINXBUILD ?= sphinx-build
SOURCEDIR = .
BUILDDIR = ../docs/documentation

.PHONY: html clean

html:
	$(SPHINXBUILD) -b html "$(SOURCEDIR)" "$(BUILDDIR)"

clean:
	rm -rf "$(BUILDDIR)"
