# Test models

This folder contains the metamodels which is ili2py tested against.

With the following commands the imd's can be updated.

ili2c versions available can be found here: https://downloads.interlis.ch/ili2c/

Build image:
```shell
docker build --build-arg ILI2C_VERSION=<desired-verion-of-ili2c> -t ili2c:latest .
```

Create IMD16 from Models:
```shell
docker run -v $(pwd)/models:/io/models --rm ili2c:latest
```

Or directly without docker:
```shell
ILI2C_EXECUTABLE="java -jar <ABSOLUTE-PATH-TO-ILI2C-JAR>" make recreate-imd
```

## Transfer data for the end-to-end tests

`tests/e2e/test_roundtrip_xtf.py` reads the transfer data of a model with the classes
generated from its imd, writes it back and validates the result with ilivalidator
(`make test-e2e`). The transfer data is selected manually and has to follow these rules:

- Put the data as plain `.xtf` next to the imd in the model folder. Use a `.zip` only if the
  `.xtf` is too big for git.
- One `.xtf` per model folder is enough. If there are several, the plain `.xtf` wins, then the
  `.xtf` in the zips in sorted order. The first one whose header section lists the model is
  used.
- The data must only contain baskets of models in the imd. E.g. data of a translated model
  needs the imd of that translation, the imd of the original model does not know it.
- The data must be valid, check it with ilivalidator in the version of the `Makefile`.
- Add the imd to the list in `tests/e2e/test_roundtrip_xtf.py`.
