from pathlib import Path

from subnocte import site


def test_links_are_relative_to_the_page_depth():
    assert site.href("home", "es", 0) == "./"
    assert site.href("home", "en", 1) == "../en/"
    assert site.href("farms", "es", 1) == "../parques.html"
    assert site.href("method", "en", 2) == "../../en/method.html"


def test_bar_marks_the_current_page_and_switches_language():
    bar = site.nav("es", "farms", 0)
    assert "href='parques.html' aria-current=page" in bar
    assert "href='en/windfarms.html' hreflang='en'" in bar
    assert bar.count("aria-current") == 1


def test_stamp_is_idempotent(tmp_path: Path):
    report = tmp_path / "output" / "r.html"
    report.parent.mkdir()
    report.write_text("<!doctype html><meta charset='utf-8'><title>R</title><style>body{}</style>\n<h1>R</h1>",
                      encoding="utf-8")
    assert site.stamp(report, tmp_path)
    once = report.read_text(encoding="utf-8")
    site.stamp(report, tmp_path)
    assert report.read_text(encoding="utf-8") == once
    assert once.count(site.START) == 1 and once.index(site.END) < once.index("<h1>")
    assert "href='../metodo.html' aria-current=page" in once and "href='../en/method.html'" in once
    assert "html{background:#fff" in once


def test_stamp_skips_missing_files(tmp_path: Path):
    assert not site.stamp(tmp_path / "nope.html", tmp_path)
