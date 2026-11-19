"""Sweeping name plate for CadQuery 2.7+.

All dimensions are millimeters; angles are degrees.
Run in CQ-editor, or run with Python to export STEP and STL files.
"""

import cadquery as cq
import math
from pathlib import Path


def sweeping_name_plate(
    lines=("Jack Abramson ", "Plant Dad"),
    font_size=20,
    line_gap=3,
    sweep_angle=75,
    font="Aldo",
    font_kind="bold",
    font_path=None,
    alignment="center",
    inner_radius=5,
    base_thickness=3,
    base_margin=3,
):
    """Return a single solid as a CadQuery Workplane.

    lines: text in top-to-bottom order. Blank lines are ignored.
    font_size: font em size, not the exact visible letter height.
    line_gap: clear gap between the actual outlines of adjacent rows.
    font_path: optional path to a TTF/OTF file for a specific font.
    alignment: 'left', 'center', or 'right'.

    Every row revolves around the same X axis. Upper rows have larger
    radii, forming concentric curves. All rows merge into the base.
    """
    if isinstance(lines, str):
        lines = lines.splitlines()
    lines = [line for line in lines if line.strip()]
    if not lines:
        raise ValueError("Enter at least one nonblank line of text.")
    if alignment not in ("left", "center", "right"):
        raise ValueError("Alignment must be left, center, or right.")
    if font_kind not in ("regular", "bold", "italic"):
        raise ValueError("Font kind must be regular, bold, or italic.")
    dimensions = (font_size, inner_radius, base_thickness, base_margin)
    if any(not math.isfinite(v) or v <= 0 for v in dimensions):
        raise ValueError("Font size, radius, base thickness, and margin must be positive.")
    if not math.isfinite(line_gap) or line_gap < 0:
        raise ValueError("Line gap must be zero or greater.")
    if not math.isfinite(sweep_angle) or not 0 < sweep_angle <= 90:
        raise ValueError("Sweep angle must be greater than 0 and at most 90 degrees.")
    if font_path is not None:
        font_path = str(Path(font_path).expanduser())
        if not Path(font_path).is_file():
            raise ValueError(f"Font file not found: {font_path}")

    # Begin slightly inside the base to guarantee a solid connection.
    overlap = min(0.5, base_thickness / 2)
    sketch_z = base_thickness - overlap
    axis_start = cq.Vector(0, 0, sketch_z)
    axis_end = cq.Vector(1, 0, sketch_z)

    letters = []
    row_y = inner_radius

    # Place the bottom row first, then work outward toward the top row.
    for text in reversed(lines):
        flat_text = cq.Compound.makeText(
            text, font_size, 0,
            font=font,
            fontPath=font_path,
            kind=font_kind,
            halign="left",
            valign="bottom",
        )
        if not flat_text.Faces():
            raise ValueError(f"No letter outlines were generated for {text!r}.")

        bb = flat_text.BoundingBox()
        x_shift = {
            "left": -bb.xmin,
            "center": -(bb.xmin + bb.xmax) / 2,
            "right": -bb.xmax,
        }[alignment]
        flat_text = flat_text.translate((x_shift, row_y - bb.ymin, sketch_z))

        # Revolving faces preserves the holes in O, A, B, etc.
        for face in flat_text.Faces():
            letters.append(cq.Solid.revolve(
                face, sweep_angle, axis_start, axis_end
            ))

        row_y += bb.ylen + line_gap

    # Fit one rectangular base under all the curved letters.
    bb = cq.Compound.makeCompound(letters).BoundingBox()
    base = cq.Solid.makeBox(
        bb.xlen + 2 * base_margin,
        bb.ylen + 2 * base_margin,
        base_thickness,
        cq.Vector(bb.xmin - base_margin, bb.ymin - base_margin, 0),
    )
    solid = base.fuse(*letters).clean()

    if not solid.isValid() or len(solid.Solids()) != 1:
        raise RuntimeError("Could not create one valid solid. Try another font or more spacing.")

    return cq.Workplane("XY").newObject([solid])


if __name__ == "__main__" or "show_object" in globals():
    # EDIT YOUR DESIGN HERE.
    result = sweeping_name_plate(
        lines=("MOE", "MAKER"),
        font_size=20,
        line_gap=3,
        sweep_angle=75,
        font="Arial",
        font_kind="bold",
        font_path=None,  # Example: r"C:\Windows\Fonts\arialbd.ttf"
        alignment="center",
        inner_radius=5,
        base_thickness=3,
        base_margin=3,
    )

    if "show_object" in globals():
        show_object(result, name="Sweeping Name Plate")
    else:
        cq.exporters.export(result, "sweeping_name_plate.step")
        cq.exporters.export(result, "sweeping_name_plate.stl",
                            tolerance=0.05, angularTolerance=0.1)
        print("Saved sweeping_name_plate.step and sweeping_name_plate.stl")
