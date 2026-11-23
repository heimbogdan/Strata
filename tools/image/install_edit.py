"""tools/image/install_edit.py - Qwen-Image-Edit-2511 for an existing Strata install.

Reuses the same sd-cli binary as text-to-image (tools/image/install.py / setup --images). Downloads the Edit-2511
DiT, Qwen2.5-VL-7B text encoder, mmproj vision tower and Comfy VAE, then writes the config's "images_edit" section
used by POST /v1/images/edits.

    python tools/image/install_edit.py --config strata-q2_0.json
    python tools/image/install_edit.py --backend vulkan --quant Q4_K_M --models-dir ~/models --print
    python tools/image/install_edit.py --config strata-q2_0.json --reuse-exe

--reuse-exe: take images.exe from the config instead of compiling again (needs an existing \"images\" section).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "image"))
import install as II  # noqa: E402
import qedit as QE  # noqa: E402
import qimage as QI  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", choices=QI.BACKENDS)
    ap.add_argument("--arch", help="the GPU architecture to compile for (CUDA: 86, ...; HIP: gfx1103, ...)")
    ap.add_argument("--quant", choices=QE.QUANTS)
    ap.add_argument("--gpu-gb", type=float, help="the GPU memory the quant is picked for (default: detected)")
    ap.add_argument("--models-dir", help="where the model files go (default: the data folder's models)")
    ap.add_argument("--config", help="a run config (strata-<model>.json) to write the \"images_edit\" section into")
    ap.add_argument("--gpu-policy", choices=["auto", "keep", "shrink", "unload"], default="auto")
    ap.add_argument("--gpu", type=int, help="the GPU's number for the image job (default: the backend's first)")
    ap.add_argument("--reuse-exe", action="store_true",
                    help="use images.exe from --config instead of compiling sd-cli again")
    ap.add_argument("--build-only", action="store_true", help="compile sd-cli only")
    ap.add_argument("--print", action="store_true", help="print the images_edit section instead of writing it")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args(argv)
    import setup as S
    gpu, amd = II.detect_gpu(S) if not (a.backend and (a.arch or a.backend in ("vulkan", "cpu"))) else (None, False)
    gpu = dict(gpu or {})
    if a.arch:
        gpu["arch"] = a.arch
    if a.gpu_gb is not None:
        gpu["vram_gb"] = a.gpu_gb
    # Same backend pick as Turbo install; quant uses Edit-2511's rule (Q4_K_M ≤16 GB).
    ns = argparse.Namespace(images="qwen-image", image_backend=a.backend, image_quant=None,
                            image_gpu_policy=a.gpu_policy, yes=a.yes)
    backend, _turbo_quant, gb = S.image_backend_choice(ns, gpu or None, amd or a.backend == "hip")
    quant = a.quant or QE.pick_quant(gb or float(gpu.get("vram_gb") or 8))
    if backend in ("cuda", "hip") and not gpu.get("arch") and not a.reuse_exe:
        S.fail(f"the {backend} build needs the GPU's architecture", "pass --arch (e.g. 86 or gfx1103)")
    S.ok(f"image edit: {quant} on {backend}" + (f" ({gb:.0f} GB GPU memory)" if gb else ""))

    lib_dirs: list = []
    if a.reuse_exe:
        if not a.config:
            S.fail("--reuse-exe needs --config", "pass a run config that already has \"images\"")
        cfg0 = json.loads(Path(a.config).read_text(encoding="utf-8-sig"))
        section0 = cfg0.get("images") or {}
        exe = Path(section0.get("exe") or "")
        if not exe.is_file():
            S.fail("no images.exe to reuse", "run tools/image/install.py first, or omit --reuse-exe")
        lib_dirs = [Path(d) for d in (section0.get("lib_dirs") or [])]
        backend = a.backend or section0.get("backend") or backend
        S.ok(f"reusing sd-cli at {exe}")
    elif a.print and not a.build_only:
        # --print alone: show the section shape without compiling (exe path is a placeholder)
        exe = Path("engine-image/sd-cli")
    else:
        exe, lib_dirs = S.build_image_engine(backend, gpu, False, False)
    if a.build_only:
        return 0

    if a.models_dir:
        models = Path(a.models_dir).expanduser()
    else:
        data, _ = S.data_folder(None)
        models = data / "models"
    section = QE.image_edit_config(backend, quant, exe, models, uma=QI.is_apu(gpu), gpu=a.gpu,
                                   lib_dirs=lib_dirs, policy=a.gpu_policy)
    if a.print and not a.config:
        print(json.dumps({"images_edit": section}, indent=1))
        return 0
    S.say("  " + QE.LICENSE_NOTE)
    for name in (quant, "vae", "llm", "llm_vision"):
        _repo, path, size, sha = QE.FILES[name]
        dst = QE.local_path(models, name)
        S.download(QE.file_url(name, S.hf_endpoint()), dst, f"edit model: {Path(path).name}")
        S.verify_sha256(dst, size, sha)
    if a.print or not a.config:
        print(json.dumps({"images_edit": section}, indent=1))
        return 0
    path = Path(a.config)
    cfg = json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}
    cfg["images_edit"] = section
    S.write_config(path, cfg)
    S.ok(f"{path.name}: image edit added (POST /v1/images/edits once the server starts again)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
