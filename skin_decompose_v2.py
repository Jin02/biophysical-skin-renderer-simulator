"""
Improved / customizable chromophore decomposition (v2).

Builds on skin_decompose.py (the paper-faithful Tsumura ICA version, left
untouched) and adds a SECOND split of the pigment-neutral substrate into:

    grayscale.png   - neutral luminance/detail map (base color removed)
    tint_color      - a single base-skin color (RGB), stored in decomp.json

So the full model becomes:
    substrate(x) = grayscale(x) * tint_color
    albedo(x)    = exp( -( D_substrate + Mscale*c_m*a_m + Hscale*c_h*a_h
                           + retone offsets ) ) ^ (1/gamma)
with D_substrate = -ln(grayscale*tint). Because tint_color is now a single
editable color, the base skin tone is a fully customizable parameter while the
grayscale map keeps pores/shading/structure.

Note: substrate ~= grayscale * tint_color drops the substrate's (tiny) chroma
residual, since the substrate is already near single-hue. Reconstruction at
default tint is therefore approximate but visually negligible.

Usage:
    py skin_decompose_v2.py selftest
    py skin_decompose_v2.py decompose  IN.png  OUTDIR  [--remove-shading]
    py skin_decompose_v2.py presets    [ROOT]                 # ROOT default skin_presets_v2
    py skin_decompose_v2.py add        IN.png "Label" [ROOT]  [--remove-shading]
"""
import sys, os, json
import numpy as np
from PIL import Image

# Reuse the v1 core (paper version stays the single source of truth).
from skin_decompose import (srgb_to_linear, linear_to_srgb_u8, decompose_arrays,
                            _encode_map, build_demo, PRESETS, _slug, _save_albedo,
                            _write_manifest, GAMMA, EPS)


def split_substrate(sub_lin, mask):
    """substrate_linear -> (baseColor RGB, luminance scalar map, lum_max)."""
    baseColor = np.maximum(sub_lin[mask].mean(axis=0), EPS)    # mean base color (linear)
    denom = float(np.dot(baseColor, baseColor))
    luminance = (sub_lin @ baseColor) / denom                 # LSQ scalar: sub ~= luminance*baseColor
    lum_max = max(float(luminance[mask].max()) if mask.any() else 1.0, 1e-6)
    return baseColor, luminance, lum_max


def _overlay(b, s):
    """Photoshop 'Overlay' blend on [0,1] values (b = base, s = blend)."""
    return np.where(b < 0.5, 2.0*b*s, 1.0 - 2.0*(1.0-b)*(1.0-s))


def save_v2(res, alpha, outdir):
    os.makedirs(outdir, exist_ok=True)
    mask = res["mask"]
    baseColor, luminance, _ = split_substrate(res["sub_lin"], mask)
    lum_mean = float(luminance[mask].mean()) if mask.any() else 1.0

    # grayscale 'detail' stored as an OVERLAY blend value: mean luminance -> 0.5
    # (neutral), so Overlay(baseColor, 0.5) == baseColor and detail adds contrast.
    detail = np.clip(0.5 * luminance / max(lum_mean, 1e-6), 0.0, 1.0)
    detail_u8 = np.round(detail * 255.0).astype(np.uint8)
    detail_u8[~mask] = 128
    Image.fromarray(detail_u8, "L").save(os.path.join(outdir, "grayscale.png"))

    melanin_u8, melaninMapScale = _encode_map(res["c_m"], mask)
    hemoglobin_u8, hemoglobinMapScale = _encode_map(res["c_h"], mask)
    Image.fromarray(melanin_u8, "L").save(os.path.join(outdir, "melanin.png"))
    Image.fromarray(hemoglobin_u8, "L").save(os.path.join(outdir, "hemoglobin.png"))

    meta = dict(gamma=GAMMA, eps=EPS, blend="overlay",
                baseColor=[round(float(c), 6) for c in baseColor],
                melaninAbsorb=res["a_m"].tolist(), hemoglobinAbsorb=res["a_h"].tolist(),
                melaninMapScale=melaninMapScale, hemoglobinMapScale=hemoglobinMapScale,
                zero=128,
                width=int(alpha.shape[1]), height=int(alpha.shape[0]),
                files=dict(grayscale="grayscale.png", melanin="melanin.png",
                           hemoglobin="hemoglobin.png"))
    with open(os.path.join(outdir, "decomp.json"), "w") as f:
        json.dump(meta, f, indent=2)
    return baseColor, lum_mean


def decompose_file(in_path, outdir, remove_shading=False):
    arr = np.asarray(Image.open(in_path).convert("RGBA"))
    res = decompose_arrays(arr[..., :3], arr[..., 3], remove_shading)
    baseColor, _ = save_v2(res, arr[..., 3], outdir)
    print(f"wrote grayscale/melanin/hemoglobin + decomp.json -> {outdir}")
    print(f"  baseColor (linear RGB) = {np.round(baseColor, 3).tolist()}")


# v2 textures use MILDER freckle/redness than v1 so they read as skin, not blotches
# (still enough sparse signal for ICA).
V2_PRESETS = [
    dict(id="freckled", label="Freckled", seed=0,  base=(0.66, 0.50, 0.43),
         n_freckles=160, freckle_amp=(0.18, 0.55), n_redspots=45, redness=0.40),
    dict(id="clear",    label="Clear",    seed=3,  base=(0.71, 0.56, 0.49),
         n_freckles=80,  freckle_amp=(0.12, 0.38), n_redspots=35, redness=0.35),
    dict(id="ruddy",    label="Ruddy",    seed=7,  base=(0.72, 0.55, 0.48),
         n_freckles=90,  freckle_amp=(0.15, 0.45), n_redspots=70, redness=0.58),
    dict(id="olive",    label="Olive",    seed=11, base=(0.54, 0.44, 0.34),
         n_freckles=120, freckle_amp=(0.18, 0.5),  n_redspots=45, redness=0.38),
    dict(id="deep",     label="Deep",     seed=17, base=(0.40, 0.29, 0.23),
         n_freckles=90,  freckle_amp=(0.22, 0.6),  n_redspots=40, redness=0.32),
]

def cmd_presets(root="skin_presets_v2"):
    os.makedirs(root, exist_ok=True)
    entries = []
    for c in V2_PRESETS:
        rgb, alpha, _ = build_demo(seed=c["seed"], base=c["base"],
                                   n_freckles=c["n_freckles"], freckle_amp=c["freckle_amp"],
                                   n_redspots=c["n_redspots"], redness=c["redness"])
        outdir = os.path.join(root, c["id"])
        _save_albedo(rgb, alpha, outdir)
        res = decompose_arrays(rgb, alpha, seed=0)
        save_v2(res, alpha, outdir)
        entries.append(dict(id=c["id"], label=c["label"], dir=c["id"]))
        print(f"  {c['label']:<10} -> {outdir}")
    _write_manifest(root, entries)
    print(f"wrote {len(entries)} v2 presets + manifest -> {root}")


def cmd_add(in_path, label, root="skin_presets_v2", remove_shading=False):
    arr = np.asarray(Image.open(in_path).convert("RGBA"))
    res = decompose_arrays(arr[..., :3], arr[..., 3], remove_shading)
    sid = _slug(label)
    outdir = os.path.join(root, sid)
    _save_albedo(arr[..., :3], arr[..., 3], outdir)
    save_v2(res, arr[..., 3], outdir)
    mpath = os.path.join(root, "manifest.json")
    man = json.load(open(mpath)) if os.path.exists(mpath) else {"presets": []}
    man["presets"] = [p for p in man["presets"] if p["id"] != sid] + \
                     [dict(id=sid, label=label, dir=sid)]
    _write_manifest(root, man["presets"])
    print(f"added v2 preset '{label}' -> {outdir}  (manifest now {len(man['presets'])})")


def cmd_selftest():
    rgb, alpha, _ = build_demo()
    res = decompose_arrays(rgb, alpha, seed=0)
    mask = res["mask"]
    baseColor, luminance, _ = split_substrate(res["sub_lin"], mask)
    lum_mean = float(luminance[mask].mean())
    detail = np.clip(0.5 * luminance / max(lum_mean, 1e-6), 0.0, 1.0)

    # Overlay(baseColor, detail) reconstruction of the substrate (display space)
    baseColor_disp = np.power(np.clip(baseColor, 0, 1), 1.0 / GAMMA)
    sub_recon = _overlay(baseColor_disp[None, None, :], detail[..., None])
    sub_recon_u8 = np.round(np.clip(sub_recon, 0, 1) * 255).astype(int)
    sub_orig_u8 = linear_to_srgb_u8(res["sub_lin"]).astype(int)
    err = np.abs(sub_recon_u8 - sub_orig_u8)[mask]

    print("=== v2 self-test (Overlay) ===")
    print("outputs: baseColor + grayscale(detail) + melanin + hemoglobin")
    print(f"baseColor (linear) = {np.round(baseColor, 3).tolist()}")
    print(f"Overlay(baseColor, detail) substrate recon 8-bit err: max={err.max()} mean={err.mean():.3f}")


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    cmd = sys.argv[1]
    rs = "--remove-shading" in sys.argv
    if cmd == "selftest":
        cmd_selftest()
    elif cmd == "decompose":
        decompose_file(sys.argv[2], sys.argv[3], remove_shading=rs)
    elif cmd == "presets":
        cmd_presets(sys.argv[2] if len(sys.argv) > 2 else "skin_presets_v2")
    elif cmd == "add":
        root = sys.argv[4] if len(sys.argv) > 4 and not sys.argv[4].startswith("--") else "skin_presets_v2"
        cmd_add(sys.argv[2], sys.argv[3], root, remove_shading=rs)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
