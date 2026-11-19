import cadquery as cq
import math

# --- Parameters (adjust these) ---
NAME_TEXT = "ONSHAPE"
BASE_RADIUS = 2.5       # inches
BASE_HEIGHT = 0.25      # inches
TEXT_HEIGHT = 0.5       # inches (font size)
TEXT_THICKNESS = 0.1    # inches (how far letters stick out)
FONT = "Arial"          # any system font name

# --- 1. Create the cylindrical base ---
base = (
    cq.Workplane("XY")
    .cylinder(BASE_HEIGHT, BASE_RADIUS)
)

# --- 2. Create the text as a flat solid on a tangent plane ---
# The text is placed on a plane tangent to the cylinder's surface.
text_plane = cq.Plane(
    origin=(BASE_RADIUS, 0, BASE_HEIGHT / 2),
    xDir=(0, 1, 0),
    normal=(1, 0, 0)
)
text_solid = (
    cq.Workplane(text_plane)
    .text(NAME_TEXT, TEXT_HEIGHT, TEXT_THICKNESS, font=FONT)
)

# --- 3. "Bend" the text by intersecting with a cylindrical shell ---
# Create a thin shell just outside the base cylinder.
shell_thickness = 0.01
shell_outer = (
    cq.Workplane("XY")
    .cylinder(BASE_HEIGHT, BASE_RADIUS + TEXT_THICKNESS + shell_thickness)
)
shell_inner = (
    cq.Workplane("XY")
    .cylinder(BASE_HEIGHT, BASE_RADIUS)
)
cylindrical_shell = shell_outer.cut(shell_inner)

# Intersect the flat text with the shell. The result is the text
# deformed to follow the cylinder's curvature.
curved_text = text_solid.intersect(cylindrical_shell)

# --- 4. Combine the base and the curved text ---
nameplate = base.union(curved_text)

# --- 5. Export as STEP ---
cq.exporters.export(nameplate, "sweeping_nameplate.step")
print("STEP file 'sweeping_nameplate.step' generated successfully.")