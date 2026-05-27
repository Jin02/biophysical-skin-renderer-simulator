"""
Offline chromophore decomposition for biophysical skin rendering.

Takes a base albedo face image and separates it into three consistent maps
using FastICA in the optical-density domain (Tsumura-style):

    substrate.png   - pigment-neutral base albedo (sRGB)
    melanin.png     - melanin concentration map     (8-bit, 128 = zero)
    hemoglobin.png  - hemoglobin concentration map  (8-bit, 128 = zero)
    decomp.json     - pigment density direction vectors a_m, a_h + map scales

Model (natural-log density domain, per pixel):
    D(x) = -ln(linear_albedo(x))
    D(x) = D_substrate(x) + c_m(x) * a_m + c_h(x) * a_h
By construction D_substrate = D - (c_m a_m + c_h a_h), so re-combining at
scale 1 reconstructs the original albedo EXACTLY (self-consistent regardless
of ICA quality). ICA only decides how the chromatic variation is split.

Usage:
    py skin_decompose.py selftest
    py skin_decompose.py demo  test_albedo.png
    py skin_decompose.py decompose  IN.png  OUTDIR  [--remove-shading]
    py skin_decompose.py presets  [ROOT]                # 5 synthetic texture presets + manifest
    py skin_decompose.py add  IN.png  "Label"  [ROOT]  [--remove-shading]   # add your own image
"""
import sys, os, json
import numpy as np
from PIL import Image

GAMMA = 2.2
EPS = 1e-3


# --- transfer functions (match the widget's gamma 2.2) -----------------------
def srgb_to_linear(u8):
    return np.power(np.clip(u8.astype(np.float64) / 255.0, 0.0, 1.0), GAMMA)

def linear_to_srgb_u8(lin):
    return np.round(np.power(np.clip(lin, 0.0, 1.0), 1.0 / GAMMA) * 255.0).astype(np.uint8)


# --- FastICA (symmetric, tanh nonlinearity) ----------------------------------
def _sym_decorr(W):
    u, _, vt = np.linalg.svd(W, full_matrices=False)
    return u @ vt

def fast_ica(Z, n_comp=2, max_iter=600, tol=1e-7, seed=0):
    """Z: (N, n_features) pre-whitened. Returns unmixing W (n_comp, n_features)."""
    rng = np.random.default_rng(seed)
    W = _sym_decorr(rng.standard_normal((n_comp, Z.shape[1])))
    N = Z.shape[0]
    for _ in range(max_iter):
        WZ = W @ Z.T                       # (n_comp, N)
        G = np.tanh(WZ)
        Gp = 1.0 - G * G
        Wn = (G @ Z) / N - Gp.mean(axis=1)[:, None] * W
        Wn = _sym_decorr(Wn)
        lim = np.max(np.abs(np.abs(np.sum(Wn * W, axis=1)) - 1.0))
        W = Wn
        if lim < tol:
            break
    return W


# --- core decomposition (operates on arrays) ---------------------------------
def decompose_arrays(rgb_u8, alpha_u8, remove_shading=False, seed=0):
    H, Wd = rgb_u8.shape[:2]
    lin = np.clip(srgb_to_linear(rgb_u8), EPS, 1.0)     # (H,W,3)
    D = -np.log(lin)                                    # density >= 0

    lum = lin.mean(axis=2)
    mask = (alpha_u8 > 10) & (lum > 0.02) & (lum < 0.999)
    Dm = D[mask]                                        # (Npix, 3)
    mu = Dm.mean(axis=0)
    Xc = Dm - mu

    if remove_shading:                                  # drop luminance (1,1,1)
        e = np.ones(3) / np.sqrt(3.0)
        Xc = Xc - np.outer(Xc @ e, e)

    # PCA -> keep top 2 (pigment plane); whiten
    cov = (Xc.T @ Xc) / Xc.shape[0]
    evals, evecs = np.linalg.eigh(cov)
    order = np.argsort(evals)[::-1]
    E = evecs[:, order[:2]]
    d2 = np.maximum(evals[order[:2]], 1e-12)
    Kw = E @ np.diag(1.0 / np.sqrt(d2))                 # (3,2) whitening
    Z = Xc @ Kw                                         # (N,2)

    W = fast_ica(Z, 2, seed=seed)
    S = W @ Z.T                                         # (2,N) unit-variance sources

    # recover 3D density direction vectors: Xc ~ S^T @ M, M (2,3)
    SSt = (S @ S.T) / S.shape[1]
    M = np.linalg.solve(SSt, (S @ Xc) / S.shape[1])     # rows = direction vectors

    a = M.copy()
    c = S.copy()
    for i in range(2):                                  # orient: absorption positive
        if a[i].sum() < 0:
            a[i], c[i] = -a[i], -c[i]

    an = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-12)
    mel = int(np.argmax(an[:, 2]))                      # melanin = max blue fraction (normalized)
    hem = 1 - mel
    a_m, a_h = a[mel], a[hem]
    cm_m, ch_m = c[mel], c[hem]

    c_m = np.zeros((H, Wd)); c_m[mask] = cm_m
    c_h = np.zeros((H, Wd)); c_h[mask] = ch_m
    pig = np.zeros((H, Wd, 3))
    pig[mask] = np.outer(cm_m, a_m) + np.outer(ch_m, a_h)
    sub_lin = np.exp(-(D - pig))                        # substrate (background unchanged)

    return dict(a_m=a_m, a_h=a_h, c_m=c_m, c_h=c_h,
                sub_lin=sub_lin, mask=mask, lin=lin)


def _encode_map(cf, mask):
    """Signed map -> 8-bit with 128 == zero. Returns (uint8, scale)."""
    amax = float(np.abs(cf[mask]).max()) if mask.any() else 1.0
    amax = max(amax, 1e-9)
    scale = 127.0 / amax
    enc = np.clip(cf * scale + 128.0, 0, 255).astype(np.uint8)
    enc[~mask] = 128                                    # background -> c = 0
    return enc, scale


def _save_decomp(res, alpha, outdir):
    os.makedirs(outdir, exist_ok=True)
    H, Wd = alpha.shape
    sub_u8 = linear_to_srgb_u8(res["sub_lin"])
    Image.fromarray(np.dstack([sub_u8, alpha]), "RGBA").save(os.path.join(outdir, "substrate.png"))
    mel_u8, m_scale = _encode_map(res["c_m"], res["mask"])
    hem_u8, h_scale = _encode_map(res["c_h"], res["mask"])
    Image.fromarray(mel_u8, "L").save(os.path.join(outdir, "melanin.png"))
    Image.fromarray(hem_u8, "L").save(os.path.join(outdir, "hemoglobin.png"))
    meta = dict(gamma=GAMMA, eps=EPS,
                a_m=res["a_m"].tolist(), a_h=res["a_h"].tolist(),
                m_scale=m_scale, h_scale=h_scale, zero=128,
                width=Wd, height=H,
                files=dict(substrate="substrate.png", melanin="melanin.png",
                           hemoglobin="hemoglobin.png"))
    with open(os.path.join(outdir, "decomp.json"), "w") as f:
        json.dump(meta, f, indent=2)


def decompose_file(in_path, outdir, remove_shading=False, seed=0):
    arr = np.asarray(Image.open(in_path).convert("RGBA"))
    res = decompose_arrays(arr[..., :3], arr[..., 3], remove_shading, seed)
    _save_decomp(res, arr[..., 3], outdir)
    print(f"wrote substrate/melanin/hemoglobin + decomp.json -> {outdir}")
    print(f"  a_m (melanin density dir)    = {np.round(res['a_m'], 3).tolist()}")
    print(f"  a_h (hemoglobin density dir) = {np.round(res['a_h'], 3).tolist()}")


# --- synthetic albedo with two known independent pigment sources -------------
# ICA needs non-Gaussian, independent sources, so both pigments are built from
# sparse splatted Gaussian spots (super-Gaussian) with independent random draws.
def _splat(H, W, centers, amps, radius):
    yy, xx = np.mgrid[0:H, 0:W]
    field = np.zeros((H, W))
    for (cy, cx), a, r in zip(centers, amps, radius):
        field += a * np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2.0 * r * r)))
    return field

def build_demo(seed=0, base=(0.62, 0.46, 0.40), n_freckles=220, freckle_amp=(0.4, 1.3),
               n_redspots=90, redness=0.9, redspot_amp=(0.25, 0.8)):
    H = W = 256
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W]
    oval = (((xx - 128) / 95.0) ** 2 + ((yy - 128) / 120.0) ** 2) <= 1.0

    sub = np.empty((H, W, 3))                           # flat skin substrate (no shading)
    sub[..., 0], sub[..., 1], sub[..., 2] = base
    D = -np.log(np.clip(sub, EPS, 1.0))

    # melanin: many small freckles (sparse, super-Gaussian)
    nM = n_freckles
    cyM = rng.integers(20, H - 20, nM); cxM = rng.integers(20, W - 20, nM)
    cm = _splat(H, W, list(zip(cyM, cxM)), rng.uniform(*freckle_amp, nM),
                rng.uniform(2.0, 4.0, nM))
    # hemoglobin: two cheek blobs + independent sparse red spots (super-Gaussian)
    nR = n_redspots
    cyH = np.r_[142, 142, rng.integers(20, H - 20, nR)]
    cxH = np.r_[95, 161, rng.integers(20, W - 20, nR)]
    ampH = np.r_[redness, redness, rng.uniform(*redspot_amp, nR)]
    radH = np.r_[22.0, 22.0, rng.uniform(2.5, 4.5, nR)]
    ch = _splat(H, W, list(zip(cyH, cxH)), ampH, radH)

    a_m_true = np.array([0.35, 0.65, 1.10])
    a_h_true = np.array([0.18, 1.05, 0.55])
    D = D + cm[..., None] * a_m_true + ch[..., None] * a_h_true
    rgb = linear_to_srgb_u8(np.exp(-D))
    alpha = np.where(oval, 255, 0).astype(np.uint8)
    return rgb, alpha, dict(cm=cm, ch=ch, a_m=a_m_true, a_h=a_h_true, mask=oval)


def cmd_demo(path):
    rgb, alpha, _ = build_demo()
    Image.fromarray(np.dstack([rgb, alpha]), "RGBA").save(path)
    print(f"wrote synthetic albedo -> {path}")


def _cos(u, v):
    return float(np.dot(u, v) / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-12))

def cmd_selftest():
    rgb, alpha, truth = build_demo()
    res = decompose_arrays(rgb, alpha, remove_shading=False, seed=0)
    m = truth["mask"] & (alpha > 10)
    cm_cos = _cos(res["a_m"], truth["a_m"])
    ch_cos = _cos(res["a_h"], truth["a_h"])
    cm_corr = float(np.corrcoef(res["c_m"][m], truth["cm"][m])[0, 1])
    ch_corr = float(np.corrcoef(res["c_h"][m], truth["ch"][m])[0, 1])
    # round-trip at scale 1
    pig = np.zeros_like(res["sub_lin"])
    pig[res["mask"]] = (np.outer(res["c_m"][res["mask"]], res["a_m"])
                        + np.outer(res["c_h"][res["mask"]], res["a_h"]))
    recon = linear_to_srgb_u8(res["sub_lin"] * np.exp(-pig))
    err = np.abs(recon.astype(int) - rgb.astype(int))[res["mask"]]
    print("=== ICA self-test (synthetic, known sources) ===")
    print(f"melanin    dir cosine = {cm_cos:+.4f}   |corr| = {abs(cm_corr):.4f}")
    print(f"hemoglobin dir cosine = {ch_cos:+.4f}   |corr| = {abs(ch_corr):.4f}")
    print(f"recovered a_m = {np.round(res['a_m'],3).tolist()}  (true {truth['a_m'].tolist()})")
    print(f"recovered a_h = {np.round(res['a_h'],3).tolist()}  (true {truth['a_h'].tolist()})")
    print(f"round-trip (scale 1) 8-bit err: max={err.max()} mean={err.mean():.3f}")


# --- texture preset library (5 varied synthetic faces) -----------------------
PRESETS = [
    dict(id="freckled", label="Freckled", seed=0,  base=(0.66, 0.50, 0.43),
         n_freckles=220, freckle_amp=(0.4, 1.3), n_redspots=80,  redness=0.85),
    dict(id="clear",    label="Clear",    seed=3,  base=(0.70, 0.55, 0.48),
         n_freckles=100, freckle_amp=(0.3, 0.8), n_redspots=55,  redness=0.70),
    dict(id="ruddy",    label="Ruddy",    seed=7,  base=(0.72, 0.54, 0.47),
         n_freckles=110, freckle_amp=(0.3, 0.9), n_redspots=120, redness=1.15),
    dict(id="olive",    label="Olive",    seed=11, base=(0.52, 0.42, 0.32),
         n_freckles=160, freckle_amp=(0.4, 1.1), n_redspots=60,  redness=0.60),
    dict(id="deep",     label="Deep",     seed=17, base=(0.38, 0.27, 0.22),
         n_freckles=120, freckle_amp=(0.5, 1.3), n_redspots=50,  redness=0.50),
]

def _slug(s):
    import re
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "tex"

def _save_albedo(rgb, alpha, outdir):
    os.makedirs(outdir, exist_ok=True)
    Image.fromarray(np.dstack([rgb, alpha]), "RGBA").save(os.path.join(outdir, "albedo.png"))

def _write_manifest(root, entries):
    with open(os.path.join(root, "manifest.json"), "w") as f:
        json.dump({"presets": entries}, f, indent=2)

def cmd_presets(root="skin_presets"):
    os.makedirs(root, exist_ok=True)
    entries = []
    for c in PRESETS:
        rgb, alpha, _ = build_demo(seed=c["seed"], base=c["base"],
                                   n_freckles=c["n_freckles"], freckle_amp=c["freckle_amp"],
                                   n_redspots=c["n_redspots"], redness=c["redness"])
        outdir = os.path.join(root, c["id"])
        _save_albedo(rgb, alpha, outdir)
        res = decompose_arrays(rgb, alpha, seed=0)
        _save_decomp(res, alpha, outdir)
        entries.append(dict(id=c["id"], label=c["label"], dir=c["id"]))
        print(f"  {c['label']:<10} -> {outdir}")
    _write_manifest(root, entries)
    print(f"wrote {len(entries)} presets + manifest -> {root}")

def cmd_add(in_path, label, root="skin_presets", remove_shading=False):
    arr = np.asarray(Image.open(in_path).convert("RGBA"))
    res = decompose_arrays(arr[..., :3], arr[..., 3], remove_shading)
    sid = _slug(label)
    outdir = os.path.join(root, sid)
    _save_albedo(arr[..., :3], arr[..., 3], outdir)
    _save_decomp(res, arr[..., 3], outdir)
    mpath = os.path.join(root, "manifest.json")
    man = json.load(open(mpath)) if os.path.exists(mpath) else {"presets": []}
    man["presets"] = [p for p in man["presets"] if p["id"] != sid] + \
                     [dict(id=sid, label=label, dir=sid)]
    _write_manifest(root, man["presets"])
    print(f"added preset '{label}' -> {outdir}  (manifest now {len(man['presets'])} presets)")


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    cmd = sys.argv[1]
    if cmd == "selftest":
        cmd_selftest()
    elif cmd == "demo":
        cmd_demo(sys.argv[2])
    elif cmd == "decompose":
        rs = "--remove-shading" in sys.argv
        decompose_file(sys.argv[2], sys.argv[3], remove_shading=rs)
    elif cmd == "presets":
        cmd_presets(sys.argv[2] if len(sys.argv) > 2 else "skin_presets")
    elif cmd == "add":
        rs = "--remove-shading" in sys.argv
        root = sys.argv[4] if len(sys.argv) > 4 and not sys.argv[4].startswith("--") else "skin_presets"
        cmd_add(sys.argv[2], sys.argv[3], root, remove_shading=rs)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
