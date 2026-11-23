"""tools/image/qedit.py - Qwen-Image-Edit-2511 for Strata's POST /v1/images/edits.

Separate from Turbo text-to-image (qimage.py). serve/images.py runs sd-cli with --ref-image and
--llm_vision; install_edit.py downloads and writes the config's "images_edit" section.
"""
from __future__ import annotations

from pathlib import Path

import qimage as QI

# Hugging Face `sha` of each repo (api/models/<repo>), 2026-11-23
REVISIONS = {
    "unsloth/Qwen-Image-Edit-2511-GGUF": "52838251db242ddd8e8d0118de36c71006d7c397",
    "unsloth/Qwen2.5-VL-7B-Instruct-GGUF": "68bb8bc4b7df5289c143aaec0ab477a7d4051aab",
    "Comfy-Org/Qwen-Image_ComfyUI": "1f12b17be14c89b026c51a91d67c32f84bb047bc",
}

_DIT = "unsloth/Qwen-Image-Edit-2511-GGUF"
_TE = "unsloth/Qwen2.5-VL-7B-Instruct-GGUF"
_VAE = "Comfy-Org/Qwen-Image_ComfyUI"

# name -> (repo, path in the repo, bytes, sha256) from LFS pointers at the pinned revisions
FILES = {
    "Q4_K_M": (_DIT, "qwen-image-edit-2511-Q4_K_M.gguf", 12_842_830_432,
               "07951f61941a81e236cbd4a9b6f250d49626b3ba518f260135bf2e01a87cf1c8"),
    "Q8_0": (_DIT, "qwen-image-edit-2511-Q8_0.gguf", 22_354_590_304,
             "0bf71797bf27dac40e3d8c1dc344309cb53f2a08beed6a96120dd77164b3806f"),
    "llm": (_TE, "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf", 4_683_072_384,
            "d16776dcd9a28d42758c2958ed3a752aabf20a305252cd64ff2be72b4a78c503"),
    "llm_vision": (_TE, "mmproj-F16.gguf", 1_354_163_040,
                   "987dd0733033fb5dd9b124d1ca926ae865572e432384eee7618b2eec3e735e17"),
    "vae": (_VAE, "split_files/vae/qwen_image_vae.safetensors", 253_806_246,
            "a70580f0213e67967ee9c95f05bb400e8fb08307e017a924bf3441223e023d1f"),
}

QUANTS = ("Q4_K_M", "Q8_0")
LICENSE_NOTE = ("Qwen-Image-Edit-2511 is under Apache 2.0: "
                "https://huggingface.co/Qwen/Qwen-Image-Edit-2511")
MODEL_DIR = "qwen-image-edit-2511"
EDIT_STEPS = 20
EDIT_CFG = 2.5
MODEL_NAME = "qwen-image-edit-2511"


def pick_quant(gpu_gb: float) -> str:
    """Q4_K_M up to 16 GB VRAM; Q8_0 above (Q8_0 alone is ~21 GB on disk)."""
    if gpu_gb <= 16:
        return "Q4_K_M"
    return "Q8_0"


def file_url(name: str, endpoint: str = "https://huggingface.co") -> str:
    repo, path, _, _ = FILES[name]
    return f"{endpoint.rstrip('/')}/{repo}/resolve/{REVISIONS[repo]}/{path}"


def local_path(models_dir: Path, name: str) -> Path:
    return Path(models_dir) / MODEL_DIR / Path(FILES[name][1]).name


def default_args(backend: str) -> list[str]:
    args = ["--diffusion-fa", "--flow-shift", "3"]
    if backend == "vulkan":
        args += ["--vae-tiling", "--vae-tile-overlap", "0.25"]
    return args


def image_edit_config(backend: str, quant: str, exe: Path, models_dir: Path, *, uma: bool = False,
                      gpu=None, lib_dirs=(), policy: str = "auto") -> dict:
    """The run config's \"images_edit\" section."""
    cfg = {
        "kind": "edit",
        "model_name": MODEL_NAME,
        "exe": str(exe),
        "backend": backend,
        "quant": quant,
        "diffusion_model": str(local_path(models_dir, quant)),
        "vae": str(local_path(models_dir, "vae")),
        "llm": str(local_path(models_dir, "llm")),
        "llm_vision": str(local_path(models_dir, "llm_vision")),
        "args": default_args(backend),
        "cfg_scale": EDIT_CFG,
        "steps": EDIT_STEPS,
        "model_args": ["qwen_image_zero_cond_t=true"],
        "gpu_policy": policy,
        "uma": bool(uma),
        "sd_cpp": QI.SD_CPP_COMMIT[:7],
    }
    if gpu is not None:
        cfg["gpu"] = gpu
    if lib_dirs:
        cfg["lib_dirs"] = [str(d) for d in lib_dirs]
    return cfg
