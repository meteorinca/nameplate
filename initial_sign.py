"""Two-part initial name sign for CadQuery 2.7+.

Produces two clean, unmodified solids meant to be 3D-printed separately
in different colors and glued together:
  1. Big bold initial letter (flat back, thick enough to stand upright).
  2. Connected cursive script name that sits across the front face.

All dimensions are in millimeters; angles are in degrees.
"""

import math
from pathlib import Path

import cadquery as cq


def _check_font(font_path):
    if font_path is not None and not Path(font_path).is_file():
        raise ValueError(f"Font file not found: {font_path}")


def _flat_text(text, size, font, font_path, kind):
    # When a specific .ttf/.otf file is given, use kind="regular" so OCCT
    # loads the exact typeface from the file without trying to synthesize
    # or substitute a different system weight.
    effective_kind = "regular" if font_path else kind
    comp = cq.Compound.makeText(
        text,
        size,
        0,
        font=font,
        fontPath=font_path,
        kind=effective_kind,
        halign="left",
        valign="bottom",
    )
    if not comp.Faces():
        raise ValueError(f"No letter outlines were generated for {text!r}.")
    return comp


def _center(shape, x=0.0, y=0.0):
    bb = shape.BoundingBox()
    return shape.translate((
        x - (bb.xmin + bb.xmax) / 2,
        y - (bb.ymin + bb.ymax) / 2,
        0,
    ))


def _extrude(faces, z0, h):
    return [
        cq.Solid.extrudeLinear(f, cq.Vector(0, 0, h)).translate((0, 0, z0))
        for f in faces
    ]


def _fuse(solids):
    solids = [s for s in solids if s is not None]
    if not solids:
        return None
    if len(solids) == 1:
        return solids[0].clean()
    try:
        return solids[0].fuse(*solids[1:]).clean()
    except Exception:
        # Fallback: fuse iteratively in case a single multi-tool fuse fails
        acc = solids[0]
        for s in solids[1:]:
            acc = acc.fuse(s)
        return acc.clean()


def initial_sign(
    name="bernardo",
    initial=None,
    initial_font="Georgia",
    initial_font_path=None,
    initial_kind="bold",
    initial_height=140,
    initial_depth=18,
    name_font="Segoe Script",
    name_font_path=None,
    name_kind="regular",
    name_size=46,
    name_depth=5,
    name_offset_x=0,
    name_offset_y=-5,
    name_angle=0,
    mirror=False,
):
    """Return (initial_solid, name_solid) CadQuery shapes.

    initial_solid spans z in [0, initial_depth].
    name_solid sits flush on the front face at z in [initial_depth, initial_depth + name_depth].
    Neither letter is modified with backers or outlines.
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("Enter a name.")
    initial = (initial or name[0].upper()).strip()[:2]
    if not initial:
        raise ValueError("Initial is empty.")

    for v, label in (
        (initial_height, "Initial height"),
        (initial_depth, "Initial thickness"),
        (name_size, "Name size"),
        (name_depth, "Name thickness"),
    ):
        if not math.isfinite(v) or v <= 0:
            raise ValueError(f"{label} must be positive.")

    for v, label in (
        (name_offset_x, "Horizontal offset"),
        (name_offset_y, "Vertical position"),
        (name_angle, "Tilt angle"),
    ):
        if not math.isfinite(v):
            raise ValueError(f"{label} must be a valid number.")

    _check_font(initial_font_path)
    _check_font(name_font_path)

    # --- Big initial: scale font so the visible letter has the exact requested height.
    probe = _flat_text(initial, 100, initial_font, initial_font_path, initial_kind)
    em = 100.0 * initial_height / probe.BoundingBox().ylen
    init_flat = _center(_flat_text(initial, em, initial_font, initial_font_path, initial_kind))
    initial_solid = _fuse(_extrude(init_flat.Faces(), 0, initial_depth))

    # --- Cursive name sitting flush on the front face (z = initial_depth).
    name_flat = _flat_text(name, name_size, name_font, name_font_path, name_kind)
    name_flat = _center(name_flat)
    if name_angle:
        name_flat = name_flat.rotate((0, 0, 0), (0, 0, 1), name_angle)
    name_flat = name_flat.translate((name_offset_x, name_offset_y, 0))
    name_solid = _fuse(_extrude(name_flat.Faces(), initial_depth, name_depth))

    if initial_solid is None or not initial_solid.isValid():
        raise RuntimeError("Could not build a valid initial letter. Try another font or size.")
    if name_solid is None or not name_solid.isValid():
        raise RuntimeError("Could not build a valid name solid. Try another font or size.")

    if mirror:
        initial_solid = initial_solid.mirror("YZ")
        name_solid = name_solid.mirror("YZ")

    return initial_solid, name_solid


if __name__ == "__main__":
    fonts_dir = Path(__file__).resolve().parent / "fonts"
    i_path = fonts_dir / "PTSerif-Bold.ttf"
    n_path = fonts_dir / "Pacifico.ttf"
    init_s, name_s = initial_sign(
        initial_font_path=str(i_path) if i_path.is_file() else None,
        name_font_path=str(n_path) if n_path.is_file() else None,
    )
    name_flat_z = name_s.translate((0, 0, -name_s.BoundingBox().zmin))
    cq.exporters.export(cq.Workplane().add(init_s), "initial_sign_initial.stl")
    cq.exporters.export(cq.Workplane().add(name_flat_z), "initial_sign_name.stl")
    print("Saved initial_sign_initial.stl and initial_sign_name.stl")
