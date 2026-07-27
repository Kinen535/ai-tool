from pathlib import Path


def test_base_template_installs_global_post_csrf_bridge():
    text = Path(
        "templates/base.html"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "V15.8 global POST CSRF bridge"
        in text
    )
    assert (
        'session.get("v158_csrf_token", "")'
        in text
    )
    assert (
        'querySelectorAll("form[method]")'
        in text
    )
    assert (
        'method !== "post"'
        in text
    )
    assert (
        'input[name="csrf_token"]'
        in text
    )
    assert (
        "actionUrl.origin !=="
        in text
    )
    assert (
        "window.location.origin"
        in text
    )
    assert (
        'hidden.name = "csrf_token"'
        in text
    )
    assert (
        "form.appendChild(hidden)"
        in text
    )
