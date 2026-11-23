# Design: OpenAI-compatible `POST /v1/images/edits` (classic img2img)

**Date:** 2026-11-23  
**Status:** Approved for planning (API approach A; optional `strength`; new UI tab; portability docs at end)  
**Scope of this slice:** classic image-to-image in Strata API + web UI. ComfyUI and instruction-edit come later.

## Decisions

| Decision | Choice | Why |
| --- | --- | --- |
| Feature order | Classic img2img first; instruction edit later | Uses existing Turbo + `sd-cli`; no new mmproj / edit weights |
| API shape | OpenAI-compatible `POST /v1/images/edits` | Matches client expectations; Strata already mirrors `/v1/images/generations` |
| Strength | Optional Strata field `strength` ∈ `[0, 1]`, default `0.75` | Classic SD img2img needs a denoise knob; OpenAI edits has none |
| UI | New tab next to Images | Same pattern as text-to-image; keeps flows separate |
| Implementation | Extend `serve/images.py` + server route (approach A) | Reuse GPU turn, auth, response, file store |
| ComfyUI | Out of this slice | User will revisit after Strata edits work |
| Portability | Decision + patch-map `.md` files when implementation finishes | So a newer Strata tree can re-apply the same changes |

## Goals

1. Accept an input image + prompt on `POST /v1/images/edits` and return images in the same response shape as generations.
2. Expose the same capability in the web UI as a dedicated tab.
3. Document decisions and a file-level change map for re-applying onto a newer Strata version.

## Non-goals (v1)

- Mask / inpainting
- Multi-image inputs
- OpenAI File API `file_id`
- Streaming / partial images
- Qwen instruction edit (`sd-cli -r` + `--llm_vision`)
- ComfyUI integration
- Bundling or launching ComfyUI

## Architecture

```
Browser (Image edit tab) ──multipart or JSON──► serve/server.py
                                                    │
                                                    ▼
                                              serve/images.py
                                                    │
                                                    ▼
                                         sd-cli --init-img … --strength …
                                                    │
                                                    ▼
                                         OpenAI-shaped ImagesResponse
```

Same GPU exclusivity as generations: one image job at a time via existing `gpu_turn`; chat waits / image waits.

## API

### Route

`POST /v1/images/edits`

- Same authentication as other `/v1/*` routes.
- If images are not configured: **404** with `code: images_not_set_up` (same message pattern as generations).
- On `sd-cli` failure: **500** with `code: image_generation_failed`.
- Validation failures: **400** `invalid_request_error`.

### Request — multipart (primary OpenAI-compatible path)

| Field | Required | Notes |
| --- | --- | --- |
| `image` | yes | PNG, JPEG, or WebP file |
| `prompt` | yes | Non-empty string (same limits as generations) |
| `n` | no | 1…`max_n` |
| `size` | no | Same rules as generations; default `1024x1024` |
| `response_format` | no | `b64_json` (default) or `url` |
| `background` | no | `auto` / `opaque` / `transparent` |
| `seed` | no | Strata extension (as on generations) |
| `steps` | no | Strata extension |
| `strength` | no | Strata extension; float `0.0–1.0`; default **0.75** |

### Request — JSON (UI / scripts)

Same fields. Source image via OpenAI edits shape:

```json
{
  "images": [{ "image_url": "data:image/png;base64,..." }],
  "prompt": "...",
  "strength": 0.75,
  "size": "1024x1024",
  "response_format": "b64_json"
}
```

v1 accepts **data URLs** (and multipart files). Do not fetch arbitrary remote `https://` URLs unless a later change explicitly adds that (security / SSRF).

Reject `file_id`, mask, multi-image arrays longer than 1, and unknown output formats other than png (same as generations).

### Response

Same as generations: `created`, `data[]` with `b64_json` or `url`, `data[].seed`, `background`, plus `strata` object including seconds, steps, backend, and **`strength`**.

## Backend (`sd-cli`)

Pinned `sd-cli` already supports:

- `-i` / `--init-img` — init image path
- `--strength` — noising/unnoising strength (library default 0.75)

Build the command like generations, then add `--init-img <temp path>` and `--strength <value>`. Write the uploaded image into the job work directory (same privacy pattern as `--prompt-file`: not left world-readable). Keep Turbo sigmas / CFG / euler / config `args` unchanged for this slice.

## UI

- New tab (label: **Image edit**), visible when `health.image_generation` is true.
- Form: file upload + preview, prompt, size, seed, optional strength (default shown as 0.75), Generate.
- Results gallery matching the Images tab (caption: size, seed, strength, elapsed, prompt).
- Call `POST /v1/images/edits` (prefer multipart from the browser).

## Code touch points (expected)

| Area | Files (approx.) |
| --- | --- |
| Image service | `serve/images.py` — parse edit request, `sd_cli_args` init/strength, run path |
| HTTP | `serve/server.py` — route + handler; allow multipart on this path |
| Tests | `serve/test_images.py` (or sibling) — parse + mocked sd-cli |
| Web | `serve/web/index.html`, `app.js`, `app.css` |
| Docs (upstream-style) | `docs/IMAGES.md` — edits section |
| Portability (local) | see below |

Exact diffs are recorded in the portability patch map after implementation.

## Testing

Without a GPU:

- Parse multipart + JSON; reject missing image, bad strength, empty prompt.
- Mock `sd-cli` success for edits; assert `--init-img` and `--strength` appear on the command.
- Health / tab visibility still gated on images setup.
- Existing generations tests remain green.

## Portability deliverables (end of implementation)

These are **local overlay docs** so a newer Strata checkout can re-apply the feature:

1. **`docs/work/images-edits-decisions.md`**  
   Short record of product/API decisions (this design’s decision table, plus any implementation deviations).

2. **`docs/work/images-edits-patch-map.md`**  
   File-by-file map: what changed, why, how to re-apply on a newer tree (search anchors, conflict hints, test commands). Prefer describing patches in terms of symbols/sections (`parse_request`, `_images`, Images tab markup) rather than brittle line numbers alone.

3. Optional: keep this design spec under `docs/superpowers/specs/` as the historical design.

When rebasing onto a newer Strata version: read the patch map first, then re-apply or cherry-pick; re-run `python -m unittest serve.test_images` (and any new edit tests).

## Later (not this slice)

- Instruction edit via `-r` + vision weights  
- Mask / inpainting  
- ComfyUI as consumer or backend  
- Multipart-only purity if JSON proves unnecessary  

## Open implementation notes

- Prefer sharing one code path for generations vs edits (mode flag) to avoid duplicating GPU/response logic.
- Server today insists on `Content-Type: application/json` for many POSTs; edits must accept `multipart/form-data` without breaking generations.
- Init image sizing: if `size` is set, follow generations’ width/height; document that extreme mismatches may stretch/letterbox per `sd-cli` behavior (verify against pinned sd.cpp during implementation and note the actual behavior in the patch map).
