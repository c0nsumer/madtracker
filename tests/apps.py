"""Letting go of an AppController a test made."""


def demo_data_dir(tmp_path, n: int):
    """A data folder holding the demo, seeded once under ``tmp_path`` and copied for each ``n``.

    A walk rebuilds its app many times from the same demo; seeding it
    each time replays two nights of scoring, so the first call seeds a
    template and the rest copy the closed file. The copy opens as a
    plain file whose newest event is the demo's tonight, which is what
    a demo start opens.
    """
    import shutil

    from madtracker.control.demo import seed_demo
    from madtracker.store import Store
    from madtracker.store.paths import DATABASE_FILE_NAME

    template = tmp_path / "demo-template"
    if not template.exists():
        template.mkdir()
        store = Store.open(template / DATABASE_FILE_NAME)
        try:
            seed_demo(store)
        finally:
            store.close()
    data_dir = tmp_path / f"data{n}"
    shutil.copytree(template, data_dir)
    return data_dir


def dispose_app(c) -> None:
    """Close the controller's file, then delete its main window and scoreboard.

    ``close()`` is the app's clean close: it lets the file go but leaves
    the windows, since the real program closes once and exits. A test
    that only closed would keep both windows alive to the end of the run,
    with their menus, help, pages and cards, gigabytes by the last test.
    The result backup's timer is tied to the main
    window, so deleting it also cancels the timer. A controller disposed
    of mid-test (a restart) and again at teardown is let go once.
    """
    from PySide6.QtCore import QCoreApplication, QEvent
    from shiboken6 import isValid

    c.close()
    for window in (c.main, c.board):
        if not isValid(window):
            continue
        window.hide()
        window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
