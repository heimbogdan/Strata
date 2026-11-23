# Design: Qwen-Image-Edit-2511 for `POST /v1/images/edits`

**Date:** 2026-11-23  
**Status:** Approved  
**Supersedes (for edit quality):** classic `--init-img`/`--strength` on Turbo for the Image edit tab

## Decisions

| Decision | Choice |
| --- | --- |
| Edit model | Qwen-Image-Edit-**2511** GGUF (Unsloth), default quant Q4_K_M on ≤16 GB |
| Generations | Unchanged Turbo via `"images"` |
| Edits | New `"images_edit"` config; `--ref-image` + `--llm_vision` + `qwen_image_zero_cond_t=true` |
| Strength | Not used for Edit-2511 (UI control removed) |
| Install | `python tools/image/install_edit.py --config strata-….json` |

## Files (pinned)

| Role | Source | File |
| --- | --- | --- |
| DiT | unsloth/Qwen-Image-Edit-2511-GGUF | `qwen-image-edit-2511-Q4_K_M.gguf` (~12.0 GB) |
| TE | unsloth/Qwen2.5-VL-7B-Instruct-GGUF | `Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf` (~4.4 GB) |
| Vision | same TE repo | `mmproj-F16.gguf` (~1.3 GB) |
| VAE | Comfy-Org/Qwen-Image_ComfyUI | `split_files/vae/qwen_image_vae.safetensors` (~242 MB) |

Sampling defaults: 20 steps, CFG 2.5, euler, `--flow-shift 3`, `--diffusion-fa`.

## API / UI

Same `/v1/images/edits` multipart + JSON data URL. Missing `"images_edit"` → 404 `images_edit_not_set_up`. Image edit tab visible when edit models are configured.
