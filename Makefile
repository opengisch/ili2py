
VENV_PATH ?= .venv
UV ?= uv
UV_RUN = $(UV) run --locked
DOCS_CONFIGURATION = docs/mkdocs.yml

# ********************
# Variable definitions
# ********************

# Package name
PACKAGE = ili2py

# **************
# Common targets
# **************

.PHONY: install
install:
	$(UV) sync --locked --no-dev

.PHONY: install-docs
install-docs:
	$(UV) sync --locked --no-dev --group docs

.PHONY: install-dev
install-dev:
	$(UV) sync --locked

.PHONY: install-test
install-test:
	$(UV) sync --locked --group test

.PHONY: build
build:
	$(UV) build

.PHONY: clean
clean:
	find ./src -name "*.pyc" -delete

.PHONY: clean-all
clean-all: clean
	rm -rf $(VENV_PATH)
	rm -rf src/$(PACKAGE).egg-info
	rm -rf docs/site
	rm -rf build
	rm -rf dist

.PHONY: git-attributes
git-attributes:
	git --no-pager diff --check `git log --oneline | tail -1 | cut --fields=1 --delimiter=' '`

.PHONY: dev
dev: install-dev

.PHONY: test-coverage
test-coverage:
	$(UV_RUN) --group test pytest -vv --cov $(PACKAGE) --cov-report term-missing:skip-covered tests

.PHONY: test
test:
	$(UV_RUN) --group test pytest -vv tests

.PHONY: tests
tests: test

.PHONY: check
check:
	$(UV_RUN) --group test mypy src/$(PACKAGE) tests

.PHONY: lint
lint:
	$(UV_RUN) ruff check .
	$(UV_RUN) ruff format --check .

.PHONY: format
format:
	$(UV_RUN) ruff check --fix .
	$(UV_RUN) ruff format .

.PHONY: doc-html
doc-html: $(DOCS_CONFIGURATION)
	rm -rf docs/site
	$(UV_RUN) --no-dev --group docs mkdocs build -f $(DOCS_CONFIGURATION) -d site

.PHONY: doc-gh-deploy
doc-gh-deploy: $(DOCS_CONFIGURATION)
	$(UV_RUN) --no-dev --group docs mkdocs gh-deploy -f $(DOCS_CONFIGURATION) -d site --force

.PHONY: doc-serve
doc-serve: $(DOCS_CONFIGURATION)
	$(UV_RUN) --no-dev --group docs mkdocs serve -f $(DOCS_CONFIGURATION)

.PHONY: updates
updates:
	$(UV) tree --outdated --depth 1

.PHONY: binary
binary:
	$(UV_RUN) pyinstaller --name ili2py --onefile --noconfirm \
		--add-data "src/ili2py:ili2py" \
		src/ili2py/cli.py

.PHONY: output-test
output-test:
	rm -rf build/ili2py_output_test
	$(UV_RUN) python src/ili2py/scripts/generate_test_output.py
	find build/ili2py_output_test/mermaid/ -type f -name "*.md" | parallel -j 4 'mmdc -i {} -o {.}.png --puppeteerConfigFile=puppeteer-config.json'
	plantuml -tpng build/ili2py_output_test/plantuml/*.puml
	plantuml -tpng build/ili2py_output_test/plantuml_role_members/*.puml
	zip -r build/ili2py_output_test.zip  build/ili2py_output_test

.PHONY: doc-diagrams
doc-diagrams:
	rm -rf build/ili2py_doc_diagrams
	$(UV_RUN) python src/ili2py/scripts/generate_docs_diagrams.py
	zip -r build/ili2py_doc_diagrams.zip  build/ili2py_doc_diagrams
	cd build/ili2py_doc_diagrams/plantuml/ && ffmpeg -framerate 2 -pattern_type glob -i "*.resized.png" output.mp4 && cd -
	ffmpeg -i build/ili2py_doc_diagrams/plantuml/output.mp4 -vf "fps=15,scale=320:-1:flags=lanczos,palettegen" build/ili2py_doc_diagrams/plantuml/palette.png
	ffmpeg -i build/ili2py_doc_diagrams/plantuml/output.mp4 -i build/ili2py_doc_diagrams/plantuml/palette.png -filter_complex "fps=15,scale=3200:-1:flags=lanczos[x];[x][1:v]paletteuse" build/ili2py_doc_diagrams/plantuml/output.gif
	# mv build/ili2py_doc_diagrams/plantuml/output.gif docs/mkdocs/assets/img/diagrams/showcase.gif

.PHONY: plantuml-showcase-diagrams
plantuml-showcase-diagrams:
	rm -rf build/plantuml_showcase_diagrams
	$(UV_RUN) python src/ili2py/scripts/generate_plantuml_diagrams.py
	zip -r build/plantuml_showcase_diagrams.zip  build/plantuml_showcase_diagrams
	cd build/plantuml_showcase_diagrams/plantuml/ && ffmpeg -framerate 2 -pattern_type glob -i "*.resized.png" output.mp4 && cd -
	ffmpeg -i build/plantuml_showcase_diagrams/plantuml/output.mp4 -vf "fps=15,scale=320:-1:flags=lanczos,palettegen" build/plantuml_showcase_diagrams/plantuml/palette.png
	ffmpeg -i build/plantuml_showcase_diagrams/plantuml/output.mp4 -i build/plantuml_showcase_diagrams/plantuml/palette.png -filter_complex "fps=15,scale=3200:-1:flags=lanczos[x];[x][1:v]paletteuse" build/plantuml_showcase_diagrams/plantuml/output.gif

.PHONY: mermaid-showcase-diagrams
mermaid-showcase-diagrams:
	rm -rf build/mermaid_showcase_diagrams
	$(UV_RUN) python src/ili2py/scripts/generate_mermaid_diagrams.py
	zip -r build/mermaid_showcase_diagrams.zip  build/mermaid_showcase_diagrams
	cd build/mermaid_showcase_diagrams/mermaid/ && ffmpeg -framerate 2 -pattern_type glob -i "*.resized.png" output.mp4 && cd -
	ffmpeg -i build/mermaid_showcase_diagrams/mermaid/output.mp4 -vf "fps=15,scale=320:-1:flags=lanczos,palettegen" build/mermaid_showcase_diagrams/mermaid/palette.png
	ffmpeg -i build/mermaid_showcase_diagrams/mermaid/output.mp4 -i build/mermaid_showcase_diagrams/mermaid/palette.png -filter_complex "fps=15,scale=3200:-1:flags=lanczos[x];[x][1:v]paletteuse" build/mermaid_showcase_diagrams/mermaid/output.gif
