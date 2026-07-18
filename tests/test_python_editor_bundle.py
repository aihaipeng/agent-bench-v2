from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]


def test_codemirror_python_bundle_is_local_and_built():
    source = (PROJECT_ROOT / "web" / "frontend" / "python-editor.js").read_text(
        encoding="utf-8"
    )
    bundle = PROJECT_ROOT / "web" / "static" / "assets" / "codemirror-python.js"

    assert bundle.is_file()
    assert bundle.stat().st_size > 100_000
    assert "python()" in source
    assert "indentWithTab" in source
    assert "cm-template-placeholder" in source
    assert "regexp: /\\$\\{" in source
    assert "model_provider|api_key|base_url|system_prompt|human_message" in source


def test_frontend_dependencies_are_locked_for_offline_rebuilds():
    package_json = (PROJECT_ROOT / "package.json").read_text(encoding="utf-8")

    assert (PROJECT_ROOT / "package-lock.json").is_file()
    assert '"build:editor"' in package_json
    assert '"codemirror"' in package_json
    assert '"@codemirror/lang-python"' in package_json
    assert '"esbuild"' in package_json
