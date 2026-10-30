# Icons

`bike.svg` is the "bike" icon from Material Design Icons by the
Pictogrammers (https://pictogrammers.com/library/mdi/icon/bike/), used
under the Pictogrammers Free License (Apache 2.0 terms). It is the app
icon.

The PNGs next to it, and `packaging/madtracker.ico` and `.icns`, are
generated from the SVG by `tools/make_icons.py`. Re-run that script after changing the SVG. The app
loads the PNGs at runtime for the window and taskbar icon.

## Interface glyphs (`mdi/`)

The SVGs in `mdi/` are also from Material Design Icons by the
Pictogrammers (https://pictogrammers.com/library/mdi/), under the same
Pictogrammers Free License (Apache 2.0 terms). They are the upstream files
from https://github.com/Templarian/MaterialDesign/tree/master/svg, unchanged.
`madtracker.ui.icons` renders them at runtime with Qt SVG and injects the
fill color, so one file serves every tint.

Each file keeps its upstream name. To add one, download it from the URL
pattern `https://raw.githubusercontent.com/Templarian/MaterialDesign/master/svg/<name>.svg`
into `mdi/` and use it through `madtracker.ui.icons.mdi(name)`.
