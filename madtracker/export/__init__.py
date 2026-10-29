"""Results outputs: archival PDF and the USAC results CSV."""

from typing import TYPE_CHECKING

from madtracker.export.usac_csv import ExportReport, write_usac_csv

if TYPE_CHECKING:
    from madtracker.export.pdf import write_results_pdf

__all__ = ["ExportReport", "write_results_pdf", "write_usac_csv"]


def __getattr__(name: str):
    # The PDF writer brings fpdf2 and fontTools, 200 to 300 ms to import
    # the first time; a CSV export needs neither, so the PDF module loads
    # only when something asks for it. The import is still a plain one
    # here, where PyInstaller's analysis finds it.
    if name == "write_results_pdf":
        from madtracker.export.pdf import write_results_pdf

        return write_results_pdf
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
