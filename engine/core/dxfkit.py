"""Shared DXF helpers for drawing engines: document setup, layers, text styles, title block, PDF print."""
from __future__ import annotations

LAYERS = {  # name: (ACI colour, linetype, description)
    "BORDER": (7, "CONTINUOUS", "sheet border"), "TITLE": (7, "CONTINUOUS", "title block"),
    "GRID": (8, "DASHED", "coordinate grid"), "EQPT": (7, "CONTINUOUS", "equipment"),
    "EQPT-TAG": (7, "CONTINUOUS", "equipment tags"), "PIPE": (5, "CONTINUOUS", "process lines"),
    "PIPE-TAG": (5, "CONTINUOUS", "line numbers"), "VALVE": (1, "CONTINUOUS", "valves / inline items"),
    "INST": (3, "CONTINUOUS", "instruments"), "INST-SIG": (3, "DASHED", "instrument connections"),
    "OFFPAGE": (6, "CONTINUOUS", "off-page connectors"), "NOTE": (8, "CONTINUOUS", "notes"),
}


def new_doc():
    import ezdxf
    doc = ezdxf.new("R2018", setup=True)          # setup=True: standard linetypes + text styles
    doc.header["$INSUNITS"] = 4                   # millimetres
    doc.header["$MEASUREMENT"] = 1
    for name, (color, lt, desc) in LAYERS.items():
        layer = doc.layers.add(name, color=color, linetype=lt)
        layer.description = desc
    doc.styles.add("ALPILLA", font="DejaVuSans.ttf")
    return doc


def text(msp, s, x, y, h, layer="NOTE", align="LEFT", rot=0.0):
    from ezdxf.enums import TextEntityAlignment
    t = msp.add_text(str(s), height=h, rotation=rot, dxfattribs={"layer": layer, "style": "ALPILLA"})
    t.set_placement((x, y), align={"LEFT": TextEntityAlignment.LEFT, "CENTER": TextEntityAlignment.CENTER,
                                   "RIGHT": TextEntityAlignment.RIGHT, "MIDDLE": TextEntityAlignment.MIDDLE_CENTER,
                                   "MIDLEFT": TextEntityAlignment.MIDDLE_LEFT}[align])
    return t


def title_block(msp, x0, y0, s, fields: list[tuple[str, str]], width, row_h):
    """Title block with its lower-right corner at (x0, y0); s = scale factor (1 for paper-mm drawings)."""
    rows = len(fields)
    x1, y1 = x0 - width * s, y0 + rows * row_h * s
    msp.add_lwpolyline([(x1, y0), (x0, y0), (x0, y1), (x1, y1)], close=True, dxfattribs={"layer": "TITLE"})
    for i, (k, v) in enumerate(reversed(fields)):
        yy = y0 + i * row_h * s
        if i:
            msp.add_line((x1, yy), (x0, yy), dxfattribs={"layer": "TITLE"})
        text(msp, k, x1 + 2 * s, yy + row_h * s / 2, 2.0 * s, "TITLE", "MIDLEFT")
        text(msp, v, x1 + 28 * s, yy + row_h * s / 2, 2.6 * s, "TITLE", "MIDLEFT")
    msp.add_line((x1 + 26 * s, y0), (x1 + 26 * s, y1), dxfattribs={"layer": "TITLE"})


def save_pdf(doc, path, paper_mm=(420, 297)):
    """Print the model space to PDF (white paper, layer colours; ACI 7 prints black)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    fig = plt.figure(figsize=(paper_mm[0] / 25.4, paper_mm[1] / 25.4))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    cfg = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.COLOR)
    Frontend(RenderContext(doc), MatplotlibBackend(ax), config=cfg).draw_layout(doc.modelspace(), finalize=True)
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def audit(doc) -> list[str]:
    auditor = doc.audit()
    return [str(e.message) for e in auditor.errors]
