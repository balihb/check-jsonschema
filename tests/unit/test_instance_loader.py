import os

import pytest

from check_jsonschema.instance_loader import InstanceLoader
from check_jsonschema.parsers import BadFileTypeError, FailedFileLoadError
from check_jsonschema.parsers.json5 import ENABLED as JSON5_ENABLED
from check_jsonschema.parsers.toml import ENABLED as TOML_ENABLED


@pytest.fixture
def in_tmp_dir(request, tmp_path):
    os.chdir(str(tmp_path))
    yield
    os.chdir(request.config.invocation_dir)


@pytest.mark.parametrize(
    "filename, default_filetype",
    [
        ("foo.json", "notarealfiletype"),
        ("foo.json", "json"),
        ("foo.json", "yaml"),
        ("foo", "json"),
        # YAML is a superset of JSON, so using the YAML loader should be safe when the
        # data is JSON
        ("foo", "yaml"),
    ],
)
def test_instanceloader_json_data(tmp_path, filename, default_filetype):
    f = tmp_path / filename
    f.write_text("{}")
    loader = InstanceLoader([str(f)], default_filetype=default_filetype)
    data = list(loader.iter_files())
    assert data == [(f, {})]


@pytest.mark.parametrize(
    "filename, default_filetype",
    [
        ("foo.yaml", "notarealfiletype"),
        ("foo.yml", "notarealfiletype"),
        ("foo.yaml", "json"),
        ("foo.yml", "json"),
        ("foo.yaml", "yaml"),
        ("foo.yml", "yaml"),
        ("foo", "yaml"),
    ],
)
def test_instanceloader_yaml_data(tmp_path, filename, default_filetype):
    f = tmp_path / filename
    f.write_text(
        """\
a:
  b:
   - 1
   - 2
  c: d
"""
    )
    loader = InstanceLoader([f], default_filetype=default_filetype)
    data = list(loader.iter_files())
    assert data == [(f, {"a": {"b": [1, 2], "c": "d"}})]


def test_instanceloader_unknown_type_nonjson_content(tmp_path):
    f = tmp_path / "foo"  # no extension here
    f.write_text("a:b")  # non-json data (cannot be detected as JSON)
    loader = InstanceLoader([f], default_filetype="unknown")
    # at iteration time, the file should error and be reported as such
    data = list(loader.iter_files())
    assert len(data) == 1
    assert isinstance(data[0], tuple)
    assert len(data[0]) == 2
    assert data[0][0] == f
    assert isinstance(data[0][1], BadFileTypeError)


@pytest.mark.parametrize(
    "enabled_flag, extension, file_content, expect_data, expect_error_message",
    [
        (
            JSON5_ENABLED,
            "json5",
            "{}",
            {},
            "pip install json5",
        ),
        (
            TOML_ENABLED,
            "toml",
            '[foo]\nbar = "baz"\n',
            {"foo": {"bar": "baz"}},
            "pip install tomli",
        ),
    ],
)
def test_instanceloader_optional_format_handling(
    tmp_path, enabled_flag, extension, file_content, expect_data, expect_error_message
):
    f = tmp_path / f"foo.{extension}"
    f.write_text(file_content)
    loader = InstanceLoader([f])
    if enabled_flag:
        # at iteration time, the file should load fine
        data = list(loader.iter_files())
        assert data == [(f, expect_data)]
    else:
        # at iteration time, an error should be raised
        data = list(loader.iter_files())
        assert len(data) == 1
        assert isinstance(data[0], tuple)
        assert len(data[0]) == 2
        assert data[0][0] == f
        assert isinstance(data[0][1], BadFileTypeError)

        # error message should be instructive
        assert expect_error_message in str(data[0])


def test_instanceloader_yaml_dup_anchor(tmp_path):
    f = tmp_path / "foo.yaml"
    f.write_text(
        """\
a:
  b: &anchor
   - 1
   - 2
  c: &anchor d
"""
    )
    loader = InstanceLoader([str(f)])
    data = list(loader.iter_files())
    assert data == [(f, {"a": {"b": [1, 2], "c": "d"}})]


@pytest.mark.parametrize(
    "file_format, filename, content",
    [
        ("json", "foo.json", '{"a":\n'),
        ("yaml", "foo.yaml", "a: {b\n"),
        ("yaml", "foo.yaml", "a: b\nc\n"),
        ("json5", "foo.json5", '{"a":\n'),
        ("toml", "foo.toml", "abc\n"),
    ],
)
def test_instanceloader_invalid_data(tmp_path, file_format, filename, content):
    if file_format == "json5" and not JSON5_ENABLED:
        pytest.skip("test requires 'json5' support")
    if file_format == "toml" and not TOML_ENABLED:
        pytest.skip("test requires 'toml' support")

    f = tmp_path / filename
    f.write_text(content)
    loader = InstanceLoader([f])
    data = list(loader.iter_files())
    assert len(data) == 1
    assert isinstance(data[0], tuple)
    assert len(data[0]) == 2
    assert data[0][0] == f
    assert isinstance(data[0][1], FailedFileLoadError)


def test_instanceloader_invalid_data_mixed_with_valid_data(tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    c = tmp_path / "c.json"
    a.write_text("{}")
    b.write_text("{")
    c.write_text('{"c":true}')

    loader = InstanceLoader([a, b, c])

    data = list(loader.iter_files())
    assert len(data) == 3

    assert data[0] == (a, {})

    assert isinstance(data[1], tuple)
    assert len(data[1]) == 2
    assert data[1][0] == b
    assert isinstance(data[1][1], FailedFileLoadError)

    assert data[2] == (c, {"c": True})


@pytest.mark.parametrize(
    "filetypes",
    (
        ("json", "yaml"),
        ("json", "json5"),
        ("yaml", "toml"),
        ("json", "yaml", "toml", "json5"),
    ),
)
def test_instanceloader_mixed_filetypes(tmp_path, filetypes):
    if not JSON5_ENABLED and "json5" in filetypes:
        pytest.skip("test requires json5")
    if not TOML_ENABLED and "toml" in filetypes:
        pytest.skip("test requires toml")
    files = {}
    file_order = []
    if "json" in filetypes:
        files["json"] = tmp_path / "F.json"
        files["json"].write_text("{}")
        file_order.append("json")
    if "yaml" in filetypes:
        files["yaml"] = tmp_path / "F.yaml"
        files["yaml"].write_text("foo: bar")
        file_order.append("yaml")
    if "json5" in filetypes:
        files["json5"] = tmp_path / "F.json5"
        files["json5"].write_text('{//hi\n"c": 1}')
        file_order.append("json5")
    if "toml" in filetypes:
        files["toml"] = tmp_path / "F.toml"
        files["toml"].write_text('[foo]  # bar\nname = "value"\n')
        file_order.append("toml")

    loader = InstanceLoader(files.values())

    data = list(loader.iter_files())
    assert len(data) == len(files)

    for i, filetype in enumerate(file_order):
        assert isinstance(data[i], tuple)
        assert len(data[i]) == 2
        path, value = data[i]
        assert path == files[filetype]
        if filetype == "json":
            assert value == {}
        elif filetype == "yaml":
            assert value == {"foo": "bar"}
        elif filetype == "json5":
            assert value == {"c": 1}
        elif filetype == "toml":
            assert value == {"foo": {"name": "value"}}
