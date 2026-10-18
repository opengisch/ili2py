[![BuildRelease](https://github.com/rudert-geoinformatik/ili2py/actions/workflows/build.yml/badge.svg?branch=master)](https://github.com/rudert-geoinformatik/ili2py/actions/workflows/build.yml)
[![BuildDocs](https://github.com/rudert-geoinformatik/ili2py/actions/workflows/docs.yml/badge.svg?branch=master)](https://github.com/rudert-geoinformatik/ili2py/actions/workflows/docs.yml)
[![ReadTheDocs](https://github.com/rudert-geoinformatik/ili2py/actions/workflows/pages/pages-build-deployment/badge.svg?branch=master)](https://github.com/rudert-geoinformatik/ili2py/actions/workflows/pages/pages-build-deployment)

# ili2py

The IlisMeta16 model in python.

## Features

**ili2py** `python package`

1. python bindings for interlis models
1. reader for IMD16 meta models
1. index with mappers to easy access IlisMeta16 elements
1. writers: PythonSource Code (can be used to read XTF), UML Charts

## Install

The package is published on PyPI as `interlis2py` (the name `ili2py` is not available on PyPI). Import package and command line tool are `ili2py`. Requires Python >= 3.12.

```shell
pip install interlis2py
# or with uv
uv add interlis2py
```

```python
import ili2py
```

```shell
ili2py --help
```

Binaries for Linux, macOS and Windows are attached to the [releases](https://github.com/rudert-geoinformatik/ili2py/releases).

## Docs

Find current version of Docs [here](https://rudert-geoinformatik.github.io/ili2py/).
