# Image edits — decisions

**Date:** 2026-11-23  
**Design:** [docs/superpowers/specs/2026-11-23-images-edits-design.md](../superpowers/specs/2026-11-23-images-edits-design.md)  
**Plan:** [docs/superpowers/plans/2026-11-23-images-edits.md](../superpowers/plans/2026-11-23-images-edits.md)  
**Re-apply guide:** [images-edits-patch-map.md](images-edits-patch-map.md)

## Decision table

| Decision | Choice | Why |
| --- | --- | --- |
| Feature order | Classic img2img first; instruction edit later | Uses existing Turbo + `sd-cli`; no new mmproj / edit weights |
| API shape | OpenAI-compatible `POST /v1/images/edits` | Matches client expectations; Strata already mirrors `/v1/images/generations` |
| Strength | Optional Strata field `strength` ∈ `[0, 1]`, default **0.75** | Classic SD img2img needs a denoise knob; OpenAI edits has none |
| UI | New **Image edit** tab next to Images | Same pattern as text-to-image; keeps flows separate |
| Implementation | Extend `serve/images.py` + server route | Reuse GPU turn, auth, response, file store |
| ComfyUI | Out of this slice | Revisit after Strata edits work |
| Portability | Decision + patch-map files when implementation finishes | So a newer Strata tree can re-apply the same changes |

## Strength (implementation note)

`strength` is optional on every edit request. When it is omitted, parse logic uses **0.75** (same default as
stable-diffusion.cpp). It is passed to `sd-cli` as `--strength` and echoed in `strata.strength` on the response.

## Non-goals (v1)

- Mask / inpainting
- Multi-image inputs (more than one source file)
- OpenAI File API `file_id`
- Streaming / partial images
- Fetching remote `https://` image URLs
- Qwen instruction edit (`sd-cli -r` + `--llm_vision`)
- ComfyUI integration or bundling

## What shipped

- Multipart (`image` + form fields) and JSON (`images[].image_url` data URLs)
- `ImageGen.run` writes `init*` via `write_init_image` and adds `--init-img` / `--strength` to the `sd-cli` command
- Server handler `_images_edits`; multipart allowed through `_foreign_page` for browser CORS
- Web tab with file upload, preview, strength control, multipart submit
- Unit and HTTP tests in `serve/test_images.py` (no GPU)