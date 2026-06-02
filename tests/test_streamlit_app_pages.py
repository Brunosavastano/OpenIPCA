"""Streamlit render smoke tests.

AppTest renders pages, not just imports the app. This catches runtime-only UI
errors such as nested expanders when reports/latest artifacts are present.
"""

from streamlit.testing.v1 import AppTest


def test_streamlit_app_renders_all_pages():
    app = AppTest.from_file("dashboard/app.py")
    app.run(timeout=60)
    assert not app.exception

    pages = list(app.sidebar.radio[0].options)
    assert pages == ["Painel executivo", "Decomposição", "Núcleos", "Difusão", "Alertas", "Metodologia"]

    for page in pages:
        app.sidebar.radio[0].set_value(page)
        app.run(timeout=60)
        assert not app.exception, f"Streamlit page failed to render: {page}"
