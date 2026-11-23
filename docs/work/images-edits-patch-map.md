# Image edits — patch map

Use this file to re-apply classic img2img (`POST /v1/images/edits`) onto a newer Strata checkout. Read
[images-edits-decisions.md](images-edits-decisions.md) and the [design spec](../superpowers/specs/2026-11-23-images-edits-design.md) first.

**Suggested order:** `serve/images.py` → `serve/test_images.py` → `serve/server.py` → `serve/web/*` → `docs/IMAGES.md`.

**Verify (no GPU):**

```sh
python -m unittest serve.test_images
node --check serve/web/app.js
```

## Conflict tips

If upstream renamed `_images` (generations handler) or reshaped the Images tab, keep the **edits** path and handlers
separate: search for `/v1/images/edits`, `parse_edit_request`, and `tab-btn-images-edit`. Generations should stay
unchanged except shared helpers (`parse_request`, `gpu_turn`, `ImageGen.run`).

---

## `serve/images.py`

**Purpose:** Parse edit requests, decode uploads, build `sd-cli` with init image and strength, run jobs.

**Anchors:**

| Symbol | Role |
| --- | --- |
| `DEFAULT_STRENGTH` (`0.75`), `MAX_EDIT_IMAGE_BYTES` | Limits |
| `parse_strength` | Validates `0…1` |
| `parse_edit_request` | `parse_request` + `strength` |
| `decode_data_url`, `decode_edit_image` | JSON data URLs only |
| `parse_multipart_edits`, `coerce_edit_form` | Multipart parsing |
| `write_init_image` | `init.png` / `.jpg` / `.webp` in job dir (`0o600`) |
| `sd_cli_args` | Adds `--init-img` and `--strength` when `job["init_img"]` set |
| `ImageGen.run` | If `image_bytes`, `write_init_image` → `init_img`; `figures["strength"]` when present |

**Re-apply:** After `parse_request`, add edit parsers and multipart helpers. In `sd_cli_args`, append init flags only
when `job.get("init_img")`. In `run`, shallow-copy the job, write init file before `sd_cli_args`, set `figures["strength"]`
in the success path. Update the module docstring to mention `/v1/images/edits`.

---

## `serve/test_images.py`

**Purpose:** Parse/decode/run tests without a GPU; HTTP tests with `fake_sd_cli.py`.

**Anchors:**

| Class / helper | Covers |
| --- | --- |
| `EditRequest` | `parse_edit_request`, strength default and bounds |
| `EditImageDecode` | data URLs, multipart roundtrip, `coerce_edit_form` |
| `EditRun` | `write_init_image`, `--init-img`, `--strength` on command |
| `EditCommand` | `sd_cli_args` with/without init |
| `Http` (existing) → `post_edits`, `test_edits_json`, `test_edits_multipart`, `test_edits_not_set_up`, `test_edits_missing_image_400` | End-to-end route |

**Re-apply:** Add classes after `Request`. Extend the `Http` test class with `post_edits` and edit POST cases. Do not
remove generation tests.

---

## `serve/server.py`

**Purpose:** Route `POST /v1/images/edits`; accept multipart from the browser without breaking JSON-only CORS rules.

**Anchors:**

| Symbol | Change |
| --- | --- |
| `_foreign_page(self, path="")` | Pass `path` from `_post`. Allow `multipart/form-data` when `path == "/v1/images/edits"`. |
| `_post` | Early branch: `if path == "/v1/images/edits": self._images_edits(); return` (before global JSON parse). |
| `_images_edits` | Same 404/400/500 pattern as generations; multipart vs JSON; attach `image_bytes` / `image_suffix`; `gpu_turn` + `gen.run`. |

**Re-apply:** Change `_foreign_page()` to `_foreign_page(self, path="")` and update the call in `_post`. Add the edits
branch and handler beside `_images` (generations). Mirror error codes: `images_not_set_up`, `image_generation_failed`,
`invalid_request_error`.

---

## `serve/web/index.html`

**Purpose:** **Image edit** tab and form.

**Anchors:**

- Tab: `id="tab-btn-images-edit"`, `data-tab="images-edit"`, label **Image edit**
- Section: `id="view-images-edit"`, form `id="imge-form"`
- Fields: `imge-file` (accept PNG/JPEG/WebP), `imge-preview`, `imge-prompt`, `imge-size`, `imge-seed`, `imge-strength` (default 0.75), `imge-go`, `imge-results`

---

## `serve/web/app.js`

**Purpose:** Tab routing, health gating, multipart submit.

**Anchors:**

- `TABS` includes `"images-edit"`
- `loadHealth`: show `tab-btn-images-edit` when `health.image_generation`
- `showTab`: focus `imge-prompt` for `images-edit`
- `imgePreviewUrl`, file `onchange` preview
- Form submit: `FormData` with `image`, `prompt`, `size`, `response_format`, optional `seed` / `strength`; `fetch("v1/images/edits", …)` with `headers(false)` (no JSON Content-Type)

---

## `serve/web/app.css`

**Purpose:** Preview styling.

**Anchor:** `.imge-preview` (max height, rounded, `object-fit: contain`).

---

## `docs/IMAGES.md`

**Purpose:** User-facing **Image edits** section (endpoint, fields, curl examples, web tab, non-goals).

**Anchor:** New section after **Request fields**, before **Sharing the GPU with the text model**.

---

## Portability files (this folder)

| File | Role |
| --- | --- |
| `images-edits-decisions.md` | Decision table + non-goals |
| `images-edits-patch-map.md` | This file |