"""Built-in help: one window, the repository's documents, a contents list (design section 5)."""

from madtracker.ui import help as help_mod


def test_pages_are_the_documents_that_exist(tmp_path):
    (tmp_path / "backups.md").write_text("# Backups\n\nText.", encoding="utf-8")
    pages = help_mod.available_pages(tmp_path)
    assert [(k, t) for k, t, _ in pages] == [("backups", "Backups")]
    assert help_mod.help_dir().as_posix().endswith("madtracker/help")
    keys = [k for k, _, _ in help_mod.available_pages()]
    assert keys == ["start", "scoring", "results", "multi_race", "backups"]
    # The rule register is for officials and developers, and installing
    # happens before the app can show its help: neither is a page.
    names = [name for _, _, name in help_mod.PAGES]
    assert "scoring-rules.md" not in names
    assert "installing.md" not in names


def test_help_window_lists_contents_and_renders_markdown(qtbot, tmp_path):
    (tmp_path / "scoring.md").write_text("# Guide\n\nClick riders.", encoding="utf-8")
    (tmp_path / "backups.md").write_text("# Backups\n\nA copy.", encoding="utf-8")
    w = help_mod.HelpWindow(folder=tmp_path)
    qtbot.addWidget(w)
    contents = w.contents
    pages = [contents.topLevelItem(i) for i in range(contents.topLevelItemCount())]
    assert [p.text(0) for p in pages] == [
        "Scoring",
        "Backups",
    ]
    assert "Click riders" in w.text.toPlainText()
    assert w.show_page("backups") and w.current_key() == "backups"
    assert "A copy" in w.text.toPlainText()
    assert not w.show_page("results"), "a page whose file is missing is not listed"


def test_help_menu_opens_the_window_on_the_page(qtbot):
    from madtracker.ui.window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    labels = [a.text().replace("&", "") for a in w.help_menu.actions() if not a.isSeparator()]
    assert labels[:-3] == [title for _, title, _ in help_mod.PAGES]
    assert labels[-3:] == ["Demo Data File...", "Open Data Folder", "About MadTracker"]
    # F1 is the help for the screen in view, not a menu item's.
    assert all(a.shortcut().isEmpty() for a in w.help_actions.values())
    assert w.help_here.shortcut().toString() == "F1"
    w.help_actions["backups"].trigger()
    assert w.help_window is not None and w.help_window.current_key() == "backups"
    w.help_actions["start"].trigger()
    assert w.help_window.current_key() == "start"


def test_a_link_to_another_page_shows_that_page(qtbot):
    from PySide6.QtCore import QUrl

    w = help_mod.HelpWindow()
    qtbot.addWidget(w)
    w.show_page("start")
    start = (help_mod.help_dir() / "getting-started.md").read_text(encoding="utf-8")
    assert "[Backups](backups.md)" in start
    w.text.anchorClicked.emit(QUrl("backups.md"))
    assert w.current_key() == "backups"
    assert w.contents.currentItem().text(0) == "Backups"
    assert "complete copy" in w.text.toPlainText()


def test_every_page_title_is_its_heading_and_its_links_text():
    """One name per page, in the contents list, on the page and in every link to
    it; a link into a section is worded from that section's heading."""
    import re

    folder = help_mod.help_dir()
    titles = {name: title for _, title, name in help_mod.PAGES}
    anchors = {
        name: {help_mod.slug(h): help_mod._plain(h) for h in _all_headings(folder / name)}
        for name in titles
    }
    # A link may also be worded as a term the target page sets in bold, such
    # as a kind of standings named inside "The four kinds".
    terms = {
        name: {t.lower() for t in re.findall(r"\*\*([^*]+)\*\*", (folder / name).read_text())}
        for name in titles
    }
    links = 0
    for name, title in titles.items():
        text = (folder / name).read_text(encoding="utf-8")
        assert text.startswith(f"# {title}\n"), name
        for label, target, fragment in re.findall(
            r"\[([^\]]+)\]\(((?:[\w-]+\.md)?)(?:#([\w-]+))?\)", text
        ):
            page = target or name
            if page not in titles:
                continue
            links += 1
            if not fragment:
                assert label == titles[page], f"{name}: [{label}]({target})"
                continue
            assert fragment in anchors[page], f"{name}: no heading for #{fragment} in {page}"
            heading = anchors[page][fragment]
            worded = label == titles[page] or label.lower() in heading.lower()
            assert worded or label.lower() in terms[page], f"{name}: [{label}](#{fragment})"
    assert links > 20, "the pages link to each other's sections"


def _all_headings(path):
    import re

    text = path.read_text(encoding="utf-8")
    return re.findall(r"^#{2,3} (.+?)\s*$", text, flags=re.MULTILINE)


def test_a_link_into_a_section_opens_the_page_there(qtbot):
    """A section link works as it does on GitHub: the page opens scrolled to the
    heading, and the contents list selects its section."""
    from PySide6.QtCore import QPoint, QUrl

    w = help_mod.HelpWindow()
    qtbot.addWidget(w)
    w.resize(1040, 700)
    w.show()
    w.show_page("start")
    w.text.anchorClicked.emit(QUrl("scoring.md#points-race-usac-2m"))
    assert (w.current_key(), w.current_section()) == ("scoring", "Points Race (USAC 2M)")
    top = w.text.cursorForPosition(QPoint(help_mod.PAGE_MARGIN, help_mod.PAGE_MARGIN))
    assert top.block().text() == "Points Race (USAC 2M)"
    # A same-page link scrolls within the page; a sub-heading selects the
    # section it falls under.
    w.text.anchorClicked.emit(QUrl("#elimination-usac-2e"))
    assert w.current_section() == "Elimination (USAC 2E)"
    w.text.anchorClicked.emit(QUrl("getting-started.md#demo-data-file"))
    assert (w.current_key(), w.current_section()) == ("start", "The data file")
    top = w.text.cursorForPosition(QPoint(help_mod.PAGE_MARGIN, help_mod.PAGE_MARGIN))
    assert top.block().text() == "Demo data file"
    # An unknown fragment opens the page at the top.
    w.text.anchorClicked.emit(QUrl("backups.md#no-such-heading"))
    assert (w.current_key(), w.current_section()) == ("backups", None)
    assert w.text.verticalScrollBar().value() == 0
    assert help_mod.slug("Sprint Final (USAC 2F) and Keirin Final (USAC 2H)") == (
        "sprint-final-usac-2f-and-keirin-final-usac-2h"
    )


def test_a_page_is_dressed_headings_callouts_and_a_readable_column(qtbot, tmp_path):
    """The page is restyled: Qt's plain Markdown puts the text against the frame in long lines."""
    from PySide6.QtGui import QTextFrame

    (tmp_path / "scoring.md").write_text(
        "# Guide\n\nIntro.\n\n**Note**: a callout.\n\n## Part\n\nBody text.\n", encoding="utf-8"
    )
    w = help_mod.HelpWindow(folder=tmp_path)
    qtbot.addWidget(w)
    w.resize(1900, 900)
    w.show()
    doc = w.text.document()
    sizes = {}
    block = doc.begin()
    while block.isValid():
        if block.text():
            sizes[block.text()] = block.begin().fragment().charFormat().fontPointSize()
        block = block.next()
    assert sizes["Guide"] == help_mod.H1_PT and sizes["Part"] == help_mod.H2_PT
    frames = [f for f in doc.rootFrame().childFrames() if isinstance(f, QTextFrame)]
    assert len(frames) == 1, "the Note paragraph is boxed"
    assert "a callout" in doc.findBlock(frames[0].firstPosition()).text()
    # A wide window keeps lines to the column; the room goes on the right.
    root = doc.rootFrame().frameFormat()
    width = w.text.viewport().width() - root.leftMargin() - root.rightMargin()
    assert width <= help_mod.COLUMN


def test_the_open_page_lists_its_sections_and_follows_the_scroll(qtbot):
    """Getting started runs to seven sections, so the contents list shows the open page's."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    w = help_mod.HelpWindow()
    qtbot.addWidget(w)
    w.resize(1040, 700)
    w.show()
    start = w._page_item("start")
    sections = [start.child(i).text(0) for i in range(start.childCount())]
    assert sections == help_mod.headings(help_mod.help_dir() / "getting-started.md")
    assert "The races" in sections and start.isExpanded()
    assert not w._page_item("scoring").isExpanded(), "only the open page shows its sections"
    assert w.show_page("start", "The races") and w.current_section() == "The races"
    bar = w.text.verticalScrollBar()
    assert bar.value() > 0
    # The heading is at the top of the view.
    top = w.text.cursorForPosition(QPoint(help_mod.PAGE_MARGIN, help_mod.PAGE_MARGIN))
    assert top.block().text() == "The races"
    # A click on a section row jumps there too, and the page is redrawn: the
    # bar's signal is what scrolls and repaints the view. Blocked, it would
    # move the bar and leave the page on screen where it was.
    moved = []
    bar.valueChanged.connect(moved.append)
    event_row = start.child(sections.index("The event"))
    rect = w.contents.visualItemRect(event_row)
    QTest.mouseClick(w.contents.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    assert moved, "the view was told to scroll"
    top = w.text.cursorForPosition(QPoint(help_mod.PAGE_MARGIN, help_mod.PAGE_MARGIN))
    assert top.block().text() == "The event" and w.current_section() == "The event"
    bar.setValue(0)
    assert w.current_section() is None and w.current_key() == "start"
    bar.setValue(bar.maximum())
    assert w.current_section() == sections[-1]
    # A section that is not there opens its page at the top.
    assert w.show_page("scoring", "No such section") and w.current_section() is None
    assert w._page_item("scoring").isExpanded() and not start.isExpanded()


def test_each_page_ends_with_a_link_to_the_next_and_the_last_does_not(qtbot):
    w = help_mod.HelpWindow()
    qtbot.addWidget(w)
    titles = [title for _key, title, _name in help_mod.PAGES]
    for (key, _title, _name), following in zip(help_mod.PAGES, [*titles[1:], None], strict=True):
        w.show_page(key)
        last = w.text.toPlainText().rstrip().splitlines()[-1]
        if following:
            assert last == f"Next: {following} \u2192", key
        else:
            assert not last.startswith("Next:")


def test_the_import_statuses_are_a_table_with_a_shaded_header(qtbot):
    from PySide6.QtGui import QTextTable

    w = help_mod.HelpWindow()
    qtbot.addWidget(w)
    w.show_page("start", "Riders")
    tables = [f for f in w.text.document().rootFrame().childFrames() if isinstance(f, QTextTable)]
    # The page's tables: the Terminology table, then the import statuses.
    assert [t.columns() for t in tables] == [3, 2]
    for table, word in zip(tables, ("Term", "Status"), strict=True):
        head = table.cellAt(0, 0)
        assert head.firstCursorPosition().block().text() == word
        assert head.format().background().color().name() == "#f0f2f5"


def test_opening_another_pages_section_selects_the_section(qtbot):
    """The new page's reset to the top never re-selects its page row over the section."""
    w = help_mod.HelpWindow()
    qtbot.addWidget(w)
    w.resize(1040, 700)
    w.show()
    bar = w.text.verticalScrollBar()
    bar.setValue(bar.maximum())
    assert w.show_page("scoring", "Win-and-Out (Club)")
    assert (w.current_key(), w.current_section()) == ("scoring", "Win-and-Out (Club)")


def test_a_callout_icon_reads_on_the_page_and_matches_the_app_s_own_box():
    """An icon that carries meaning reaches WCAG's 3:1 on the white page, and a
    Caution is marked as the app's warning box is."""
    from PySide6.QtGui import QColor

    from madtracker.board.theme import contrast
    from madtracker.ui import help as h
    from madtracker.ui.icons import BOX_ICONS

    for word, (_glyph, color) in h.CALLOUT_ICONS.items():
        assert contrast(QColor(color), QColor("#ffffff")) >= 3, word
    assert h.CALLOUT_ICONS["Caution"] == BOX_ICONS["warning"]


def test_back_and_forward_step_through_the_places_visited(qtbot):
    """The pages link into each other's sections, so the window keeps a
    history as a browser does: Back returns to the place left, at the scroll
    position the reader got to there, Forward retraces, and a new place after
    a step back drops what was ahead. The platform's Back and Forward keys do
    the same, and nothing is on a bare key."""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QKeySequence
    from PySide6.QtTest import QTest

    w = help_mod.HelpWindow()
    qtbot.addWidget(w)
    w.resize(1040, 700)
    w.show()
    w.show_page("start")
    assert not w.back.isEnabled() and not w.forward.isEnabled()
    assert w.back.toolTip() == "Back" and w.forward.toolTip() == "Forward"
    side = w.back.width()
    assert side == w.back.height() == w.forward.width() == w.forward.height()
    # Read down the page, then follow a link into another page's section.
    w.text.verticalScrollBar().setValue(300)
    w.text.anchorClicked.emit(QUrl("scoring.md#points-race-usac-2m"))
    assert w.current_key() == "scoring" and w.back.isEnabled() and not w.forward.isEnabled()
    w.back.click()
    assert w.current_key() == "start"
    assert w.text.verticalScrollBar().value() == 300, "back is where the reader was, not the top"
    assert not w.back.isEnabled() and w.forward.isEnabled()
    w.forward.click()
    assert (w.current_key(), w.current_section()) == ("scoring", "Points Race (USAC 2M)")
    assert not w.forward.isEnabled()
    # The contents list is a place too, and a new place drops what was ahead.
    w.back.click()
    w.show_page("backups")
    assert w.current_key() == "backups" and not w.forward.isEnabled()
    w.back.click()
    assert w.current_key() == "start" and w.forward.isEnabled()
    # The keys.
    w.activateWindow()
    QTest.qWait(10)
    forward = QKeySequence(QKeySequence.StandardKey.Forward)[0]
    QTest.keyClick(w, forward.key(), forward.keyboardModifiers())
    assert w.current_key() == "backups"
    back = QKeySequence(QKeySequence.StandardKey.Back)[0]
    QTest.keyClick(w, back.key(), back.keyboardModifiers())
    assert w.current_key() == "start"
    assert all(a.shortcut().isEmpty() or a.shortcut()[0].keyboardModifiers() for a in w.actions())
    # Stepping at the end of the history is nothing, not an error.
    w._step(-5)
    assert w.current_key() == "start"
