"""Web app for the name plate generators.

Modes:
  * initial - two-part big initial + cursive name sign (initial_sign.py)
  * plate   - sweeping curved-text name plate (sweeping_name_plate.py)

Run:  pip install -r requirements.txt
      python app.py
Then open http://127.0.0.1:5000
"""

import hashlib
import io
import json
import os
import tempfile
import threading
import zipfile
from pathlib import Path

import cadquery as cq
from flask import Flask, jsonify, render_template, request, send_file

from initial_sign import initial_sign
from sweeping_name_plate import sweeping_name_plate

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = Path(tempfile.gettempdir()) / "nameplate_fonts"
UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

_cache = {}
_cache_order = []
_lock = threading.Lock()  # OCC is not thread-safe; serialize builds
CACHE_MAX = 20

FONT_META = {
    "Pacifico.ttf": ("Pacifico", "cursive"),
    "Lobster.ttf": ("Lobster", "cursive"),
    "GrandHotel.ttf": ("Grand Hotel", "cursive"),
    "KaushanScript.ttf": ("Kaushan Script", "cursive"),
    "Cookie.ttf": ("Cookie", "cursive"),
    "PTSerif-Bold.ttf": ("PT Serif Bold", "serif"),
    "AbrilFatface.ttf": ("Abril Fatface", "serif"),
    "Aldo.ttf": ("Aldo", "display"),
}


def bundled_fonts():
    found = []
    seen = set()
    for folder in (BASE_DIR / "fonts", BASE_DIR):
        if folder.is_dir():
            for p in sorted(folder.iterdir()):
                if p.suffix.lower() in (".ttf", ".otf") and p.name not in seen:
                    seen.add(p.name)
                    found.append(p)
    return found


def font_choices():
    """Return structured list of bundled fonts for the UI."""
    choices = []
    for p in bundled_fonts():
        label, group = FONT_META.get(p.name, (p.stem, "other"))
        choices.append({"file": p.name, "label": label, "group": group})
    order = {"serif": 0, "cursive": 1, "display": 2, "other": 3}
    choices.sort(key=lambda c: (order.get(c["group"], 9), c["label"].lower()))
    return choices


def _num(form, key, default):
    raw = form.get(key, "")
    try:
        return float(raw) if raw != "" else default
    except ValueError:
        raise ValueError(f"'{key}' must be a number.")


def resolve_font(form, files, prefix, default_name):
    """Return (font_name, font_path, upload_id) for a font picker."""
    source = form.get(f"{prefix}font_source", "system")
    if source == "upload":
        f = files.get(f"{prefix}font_file")
        if f and f.filename:
            suffix = Path(f.filename).suffix.lower()
            if suffix not in (".ttf", ".otf"):
                raise ValueError("Uploaded font must be a .ttf or .otf file.")
            data = f.read()
            path = UPLOAD_DIR / f"{hashlib.sha1(data).hexdigest()[:16]}{suffix}"
            path.write_bytes(data)
        elif form.get(f"{prefix}font_upload_id"):
            path = UPLOAD_DIR / Path(form[f"{prefix}font_upload_id"]).name
            if not path.is_file():
                raise ValueError("Uploaded font expired; please upload it again.")
        else:
            raise ValueError("Choose a font file to upload.")
        return path.stem, str(path), path.name
    if source == "system":
        return (form.get(f"{prefix}font_name", "").strip() or default_name), None, None
    match = [p for p in bundled_fonts() if p.name == Path(source).name]
    if not match:
        raise ValueError("Selected bundled font not found.")
    return match[0].stem, str(match[0]), None


def parse(form, files):
    mode = form.get("mode", "initial")
    uploads = {}
    if mode == "initial":
        f1, p1, uploads["i_"] = resolve_font(form, files, "i_", "Georgia")
        f2, p2, uploads["n_"] = resolve_font(form, files, "n_", "Segoe Script")
        params = dict(
            name=form.get("name", ""),
            initial=form.get("initial", "") or None,
            initial_font=f1,
            initial_font_path=p1,
            initial_kind=form.get("i_font_kind", "bold"),
            initial_height=_num(form, "initial_height", 140),
            initial_depth=_num(form, "initial_depth", 18),
            name_font=f2,
            name_font_path=p2,
            name_kind=form.get("n_font_kind", "regular"),
            name_size=_num(form, "name_size", 46),
            name_depth=_num(form, "name_depth", 5),
            name_offset_x=_num(form, "name_offset_x", 0),
            name_offset_y=_num(form, "name_offset_y", -5),
            name_angle=_num(form, "name_angle", 0),
        )
    else:
        mode = "plate"
        font, path, uploads["p_"] = resolve_font(form, files, "p_", "Arial")
        params = dict(
            lines=tuple(form.get("lines", "").splitlines()),
            font_size=_num(form, "font_size", 20),
            line_gap=_num(form, "line_gap", 3),
            sweep_angle=_num(form, "sweep_angle", 75),
            font_kind=form.get("p_font_kind", "bold"),
            alignment=form.get("alignment", "center"),
            inner_radius=_num(form, "inner_radius", 5),
            base_thickness=_num(form, "base_thickness", 3),
            base_margin=_num(form, "base_margin", 3),
            font=font,
            font_path=path,
        )
    return mode, params, {k: v for k, v in uploads.items() if v}


def _export(shape, fmt, tmp, name):
    path = os.path.join(tmp, f"{name}.{fmt}")
    wp = cq.Workplane("XY").add(shape)
    if fmt == "stl":
        cq.exporters.export(wp, path, tolerance=0.05, angularTolerance=0.1)
    else:
        cq.exporters.export(wp, path)
    return Path(path).read_bytes()


def build(mode, params):
    key = hashlib.sha1(json.dumps([mode, params], sort_keys=True).encode()).hexdigest()
    with _lock:
        if key in _cache:
            return key, _cache[key]

        if mode == "initial":
            init_solid, name_solid = initial_sign(**params)
            parts = {"base": init_solid, "accent": name_solid}
        else:
            parts = {"base": sweeping_name_plate(**params).val()}

        combined = cq.Compound.makeCompound(list(parts.values()))
        bb = combined.BoundingBox()
        with tempfile.TemporaryDirectory() as tmp:
            # Preview STLs keep assembled positions so the 3D viewer aligns them.
            files = {f"{n}.stl": _export(s, "stl", tmp, n) for n, s in parts.items()}
            files["model.stl"] = _export(combined, "stl", tmp, "model")

            if mode == "initial":
                # Standalone print-ready STLs, each flat on the Z=0 build plate.
                files["initial.stl"] = files["base.stl"]
                name_z0 = parts["accent"].translate((0, 0, -parts["accent"].BoundingBox().zmin))
                files["name.stl"] = _export(name_z0, "stl", tmp, "name_flat")

                assy = cq.Assembly()
                assy.add(parts["base"], name="initial", color=cq.Color(0.85, 0.2, 0.25))
                assy.add(parts["accent"], name="name", color=cq.Color(1, 0.85, 0.2))
                step = os.path.join(tmp, "model.step")
                assy.save(step)
                files["model.step"] = Path(step).read_bytes()
            else:
                files["model.step"] = _export(combined, "step", tmp, "model")

        zbuf = io.BytesIO()
        with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
            if mode == "initial":
                z.writestr("initial.stl", files["initial.stl"])
                z.writestr("name.stl", files["name.stl"])
                z.writestr("assembled.step", files["model.step"])
            else:
                z.writestr("plate.stl", files["model.stl"])
                z.writestr("plate.step", files["model.step"])
        files["parts.zip"] = zbuf.getvalue()

        info = {
            "mode": mode,
            "parts": list(parts),
            "size": [round(bb.xlen, 1), round(bb.ylen, 1), round(bb.zlen, 1)],
            "volume": round(sum(s.Volume() for s in parts.values()), 1),
            "pieces": sum(len(s.Solids()) for s in parts.values()),
        }
        if mode == "initial":
            info["name_pieces"] = len(parts["accent"].Solids())

        entry = {"files": files, "info": info}
        _cache[key] = entry
        _cache_order.append(key)
        while len(_cache_order) > CACHE_MAX:
            _cache.pop(_cache_order.pop(0), None)
        return key, entry


@app.route("/")
def index():
    choices = font_choices()
    names = {c["file"] for c in choices}
    default_initial_font = "PTSerif-Bold.ttf" if "PTSerif-Bold.ttf" in names else "system"
    default_name_font = "Pacifico.ttf" if "Pacifico.ttf" in names else "system"
    return render_template(
        "index.html",
        fonts=choices,
        default_initial_font=default_initial_font,
        default_name_font=default_name_font,
    )


@app.post("/api/generate")
def generate():
    try:
        mode, params, uploads = parse(request.form, request.files)
        key, entry = build(mode, params)
    except (ValueError, RuntimeError) as e:
        return jsonify(error=str(e)), 400
    except Exception as e:  # OCC / font errors
        return jsonify(error=f"Generation failed: {e}"), 500
    return jsonify(id=key, uploads=uploads, **entry["info"])


@app.get("/api/model/<key>/<fname>")
def model(key, fname):
    entry = _cache.get(key)
    if not entry or fname not in entry["files"]:
        return jsonify(error="Model not found; please regenerate."), 404
    name = request.args.get("name", "name_plate")
    safe = "".join(c for c in name if c.isalnum() or c in "-_ ").strip() or "name_plate"
    stem, ext = fname.rsplit(".", 1)
    suffix = "" if stem == "model" else f"_{stem}"
    return send_file(
        io.BytesIO(entry["files"][fname]),
        mimetype="application/octet-stream",
        as_attachment=request.args.get("download") == "1",
        download_name=f"{safe}{suffix}.{ext}",
    )


if __name__ == "__main__":
    app.run(debug=True, threaded=True)
