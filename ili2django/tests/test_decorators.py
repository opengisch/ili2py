from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ili2django.decorators import ili_field, interlis_model


@interlis_model(oid="Model.Topic.Class", qname="model.topic.Class")
class Demo:
    pass


def test_interlis_model_decorator_sets_metadata():
    assert Demo.__ili2django__["oid"] == "Model.Topic.Class"
    assert Demo.__ili2django__["qname"] == "model.topic.Class"


def test_ili_field_sets_metadata():
    class DummyField:
        pass

    field = DummyField()
    wrapped = ili_field(field, oid="Model.Topic.Class.attr", qname="model.topic.Class.attr")
    assert wrapped is field
    assert wrapped._ili2django["oid"] == "Model.Topic.Class.attr"
