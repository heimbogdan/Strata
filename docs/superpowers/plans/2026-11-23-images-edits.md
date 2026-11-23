# Image edits (`POST /v1/images/edits`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add OpenAI-compatible classic image-to-image via `POST /v1/images/edits` (optional `strength`, default 0.75) and a new **Image edit** web tab, plus portability docs for re-applying onto a newer Strata tree.

**Architecture:** Extend `serve/images.py` so one job dict can carry an init image path + strength; build `sd-cli` with `--init-img` and `--strength`. Route multipart/JSON in `serve/server.py` before the global `json.loads` path. Reuse `gpu_turn`, response/store, and the fake `sd-cli` test fixture. UI mirrors the Images tab.

**Tech Stack:** Python stdlib HTTP server (`serve/server.py`), `serve/images.py`, `sd-cli` (`--init-img` / `--strength`), unittest (`serve/test_images.py`), vanilla web (`serve/web/*`).

**Spec:** `docs/superpowers/specs/2026-11-23-images-edits-design.md`

## Global Constraints

- Classic img2img only (no mask, multi-image, `file_id`, streaming, or `-r` instruction edit).
- Optional `strength` ∈ `[0.0, 1.0]`; omit → `0.75` (matches `sd-cli` default).
- Accept multipart `image` and JSON `images[0].image_url` **data URLs** only (no remote fetch).
- Same auth, GPU exclusivity, and response shape as `/v1/images/generations`.
- Do **not** create git commits unless the user explicitly asks.
- Docs style: plain words, short sentences (see `AGENTS.md`).

## File map

| File | Responsibility |
| --- | --- |
| `serve/images.py` | Parse edit fields; write init image; extend `sd_cli_args` / `ImageGen.run` / response `strata.strength` |
| `serve/server.py` | Multipart branch for `/v1/images/edits`; allow multipart from allowed Origin; `_images_edits` handler |
| `serve/fixtures/fake_sd_cli.py` | Accept `--init-img` / `--strength` (ignore contents beyond existing behavior) |
| `serve/test_images.py` | Unit + HTTP tests for edits |
| `serve/web/index.html` | Image edit tab + form |
| `serve/web/app.js` | Tab visibility + submit to `/v1/images/edits` |
| `serve/web/app.css` | Minimal styles for upload/preview if needed |
| `docs/IMAGES.md` | Document edits endpoint |
| `docs/work/images-edits-decisions.md` | Decision record (portability) |
| `docs/work/images-edits-patch-map.md` | File-level re-apply guide (portability) |

---

### Task 1: Parse edit request + `sd_cli_args` with init image

**Files:**
- Modify: `serve/images.py`
- Test: `serve/test_images.py`

**Interfaces:**
- Produces: `DEFAULT_STRENGTH = 0.75`
- Produces: `parse_strength(value) -> float` raising `ImageRequestError`
- Produces: `parse_edit_request(req: dict, cfg: dict) -> dict` — same keys as `parse_request`, plus `strength: float`, and **no** image bytes yet (image handled when building the job / writing files)
- Produces: `write_init_image(work: Path, data: bytes, suffix: str) -> Path` — owner-only file like `write_prompt`
- Produces: `sd_cli_args(...)` adds `--init-img` and `--strength` when `job` has `init_img` (path string) and `strength`
- Consumes: existing `parse_request` field rules for prompt/size/n/steps/seed/response_format/background

- [ ] **Step 1: Write the failing tests**

Add to `serve/test_images.py`:

```python
class EditRequest(unittest.TestCase):
    CFG = {"max_n": 4, "max_side": 2048}

    def test_defaults_include_strength(self):
        j = images_api.parse_edit_request({"prompt": "a cat"}, self.CFG)
        self.assertEqual(j["strength"], 0.75)
        self.assertEqual((j["width"], j["height"], j["n"], j["steps"]), (1024, 1024, 1, 8))

    def test_strength_ok_and_refused(self):
        self.assertEqual(images_api.parse_edit_request({"prompt": "x", "strength": 0.4}, self.CFG)["strength"], 0.4)
        self.assertEqual(images_api.parse_edit_request({"prompt": "x", "strength": 0}, self.CFG)["strength"], 0.0)
        self.assertEqual(images_api.parse_edit_request({"prompt": "x", "strength": 1}, self.CFG)["strength"], 1.0)
        for bad in (True, "0.5", -0.1, 1.1, 2):
            with self.subTest(bad=bad), self.assertRaises(images_api.ImageRequestError):
                images_api.parse_edit_request({"prompt": "x", "strength": bad}, self.CFG)


class EditCommand(unittest.TestCase):
    def test_init_img_and_strength_on_command(self):
        cfg = {"exe": "sd-cli", "diffusion_model": "d", "vae": "v", "llm": "l", "args": ["--diffusion-fa"]}
        job = {"prompt": "p", "width": 512, "height": 512, "n": 1, "steps": 8, "seed": 1,
               "strength": 0.4, "init_img": "work/init.png"}
        cmd = images_api.sd_cli_args(cfg, job, "x", "p.txt")
        self.assertEqual(cmd[cmd.index("--init-img") + 1], "work/init.png")
        self.assertEqual(cmd[cmd.index("--strength") + 1], "0.4")
        # generations (no init_img) unchanged:
        job2 = {k: v for k, v in job.items() if k not in ("init_img", "strength")}
        self.assertNotIn("--init-img", images_api.sd_cli_args(cfg, job2, "x", "p.txt"))
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `python -m unittest serve.test_images.EditRequest serve.test_images.EditCommand -v`  
Expected: FAIL (`parse_edit_request` / missing flags)

- [ ] **Step 3: Implement parsing + command flags**

In `serve/images.py`:

```python
DEFAULT_STRENGTH = 0.75

def parse_strength(value) -> float:
    if value is None:
        return DEFAULT_STRENGTH
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not (0.0 <= float(value) <= 1.0):
        raise ImageRequestError("strength: a number from 0 to 1")
    return float(value)

def parse_edit_request(req: dict, cfg: dict) -> dict:
    job = parse_request(req, cfg)
    job["strength"] = parse_strength(req.get("strength"))
    return job

def write_init_image(work: Path, data: bytes, suffix: str = ".png") -> Path:
    if suffix not in (".png", ".jpg", ".jpeg", ".webp"):
        suffix = ".png"
    path = work / f"init{suffix}"
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as f:
        f.write(data)
    return path
```

In `sd_cli_args`, after size/seed/batch and before `-o` (or immediately after `-o` is fine if consistent — prefer **after** height, **before** `-o`):

```python
    if job.get("init_img"):
        cmd += ["--init-img", str(job["init_img"]), "--strength", str(job.get("strength", DEFAULT_STRENGTH))]
```

Do **not** put `--strength` on pure generations jobs (no `init_img`).

- [ ] **Step 4: Run tests — expect PASS**

Run: `python -m unittest serve.test_images.EditRequest serve.test_images.EditCommand -v`  
Expected: PASS

Also run: `python -m unittest serve.test_images.Command -v`  
Expected: PASS (generations command unchanged)

---

### Task 2: Decode edit image bytes (JSON data URL + multipart helpers)

**Files:**
- Modify: `serve/images.py`
- Test: `serve/test_images.py`

**Interfaces:**
- Produces: `decode_edit_image(req: dict) -> tuple[bytes, str]` — `(raw_bytes, suffix)` from JSON body; raises `ImageRequestError`
- Produces: `decode_data_url(url: str) -> tuple[bytes, str]`
- Produces: `parse_multipart_edits(body: bytes, content_type: str) -> dict` — returns a dict with `prompt`, optional fields as strings/numbers, and `image_bytes` + `image_suffix`

- [ ] **Step 1: Write the failing tests**

```python
class EditImageDecode(unittest.TestCase):
    def test_data_url_png(self):
        raw = b"\x89PNG\r\n\x1a\n" + b"xxxx"
        url = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
        data, suffix = images_api.decode_edit_image({"images": [{"image_url": url}], "prompt": "x"})
        self.assertEqual(data, raw)
        self.assertEqual(suffix, ".png")

    def test_refuses_remote_url_and_empty(self):
        with self.assertRaises(images_api.ImageRequestError):
            images_api.decode_edit_image({"images": [{"image_url": "https://example.com/a.png"}], "prompt": "x"})
        with self.assertRaises(images_api.ImageRequestError):
            images_api.decode_edit_image({"prompt": "x"})
        with self.assertRaises(images_api.ImageRequestError):
            images_api.decode_edit_image({"images": [{"image_url": "data:image/png;base64,!!!!"}], "prompt": "x"})

    def test_multipart_roundtrip(self):
        # Build a minimal multipart body with image + prompt + strength
        boundary = "----strataedit"
        png = b"\x89PNG\r\n\x1a\n" + b"abcd"
        parts = []
        def part(name, value, filename=None, ctype="application/octet-stream"):
            disp = f'form-data; name="{name}"'
            if filename:
                disp += f'; filename="{filename}"'
            head = f"--{boundary}\r\nContent-Disposition: {disp}\r\n"
            if filename:
                head += f"Content-Type: {ctype}\r\n"
            head += "\r\n"
            if isinstance(value, str):
                value = value.encode()
            return head.encode() + value + b"\r\n"
        body = (part("prompt", "make it blue") + part("strength", "0.4")
                + part("image", png, filename="in.png", ctype="image/png")
                + f"--{boundary}--\r\n".encode())
        req = images_api.parse_multipart_edits(body, f"multipart/form-data; boundary={boundary}")
        self.assertEqual(req["prompt"], "make it blue")
        self.assertEqual(req["strength"], "0.4")  # raw form string; parse_edit_request coerces later — OR coerce here; pick one and test that parse_edit_request gets float
        self.assertEqual(req["image_bytes"], png)
```

Clarify in implementation: `parse_multipart_edits` returns string form fields; caller runs `parse_edit_request` after coercing numeric fields (`strength`, `n`, `seed`, `steps`) from strings. Prefer a helper `coerce_edit_form(fields: dict) -> dict` that converts known numeric keys then calls `parse_edit_request`, and leaves `image_bytes` aside.

- [ ] **Step 2: Run — expect FAIL**

Run: `python -m unittest serve.test_images.EditImageDecode -v`

- [ ] **Step 3: Implement decode helpers**

Use stdlib only: `email.parser.BytesParser` + `email.policy.default`, or manual boundary split. Accept MIME types `image/png`, `image/jpeg`, `image/webp` (map to `.png` / `.jpg` / `.webp`). Reject SVG and empty bodies. Max image size: reuse `body_limit()` conceptually — cap decoded image at e.g. 25_000_000 bytes to match MCP media spirit; document in code comment.

For JSON:

```python
def decode_edit_image(req: dict) -> tuple[bytes, str]:
    images = req.get("images")
    if not isinstance(images, list) or len(images) != 1 or not isinstance(images[0], dict):
        raise ImageRequestError("images: exactly one object with image_url (data URL)")
    url = images[0].get("image_url")
    if images[0].get("file_id"):
        raise ImageRequestError("file_id is not supported")
    return decode_data_url(url)
```

- [ ] **Step 4: Run — expect PASS**

Run: `python -m unittest serve.test_images.EditImageDecode -v`

---

### Task 3: `ImageGen.run` writes init image; response includes strength

**Files:**
- Modify: `serve/images.py` (`ImageGen.run`, `ImageGen.response` / figures)
- Test: `serve/test_images.py`

**Interfaces:**
- Consumes: `job["image_bytes"]` + `job["image_suffix"]` optional; if present, `write_init_image` then set `job["init_img"]` before `sd_cli_args`
- Produces: `figures["strength"]` when edit job

- [ ] **Step 1: Write failing HTTP-level test (uses fake sd-cli)**

Extend the existing HTTP harness pattern in `serve/test_images.py` (class that starts `serve` with `image_cfg`). Add:

```python
def test_edits_json_passes_init_and_strength(self):
    png = b"\x89PNG\r\n\x1a\n" + b"init"
    url = "data:image/png;base64," + base64.b64encode(png).decode()
    args_path = Path(self.tmpdir) / "args.json"
    with mock.patch.dict(os.environ, {"FAKE_SD_ARGS": str(args_path)}):
        code, body = self.post_edits({
            "prompt": "a blue cat", "seed": 9, "size": "512x512", "strength": 0.4,
            "images": [{"image_url": url}],
        })
    self.assertEqual(code, 200, body)
    self.assertEqual(body["strata"]["strength"], 0.4)
    argv = json.loads(args_path.read_text(encoding="utf-8"))
    self.assertIn("--init-img", argv)
    self.assertEqual(argv[argv.index("--strength") + 1], "0.4")
```

Add `post_edits` helper posting to `/v1/images/edits` with JSON (route may still 404 until Task 4 — this task can unit-test `ImageGen.run` with a patched `sd_cli_args` / fake exe instead if preferred).

Prefer **unit test on `ImageGen.run`** here (no HTTP):

```python
class EditRun(unittest.TestCase):
    def test_run_writes_init_and_records_strength(self):
        # tempfile cfg with fake_args patch like existing ImageHTTP tests
        ...
        job = images_api.parse_edit_request({"prompt": "x", "seed": 1, "size": "512x512", "strength": 0.4}, cfg)
        job["image_bytes"] = b"\x89PNG\r\n\x1a\nxx"
        job["image_suffix"] = ".png"
        with mock.patch.dict(os.environ, {"FAKE_SD_ARGS": str(args_path)}):
            with mock.patch.object(images_api, "sd_cli_args", side_effect=fake_args):
                images, figures = gen.run(job)
        self.assertEqual(figures["strength"], 0.4)
        argv = json.loads(args_path.read_text())
        self.assertIn("--init-img", argv)
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement in `ImageGen.run`**

After creating `work`, if `job.get("image_bytes")` is set:

```python
            init_path = write_init_image(work, job["image_bytes"], job.get("image_suffix") or ".png")
            job = {**job, "init_img": str(init_path)}
```

Include `"strength": job.get("strength")` in `figures` when `init_img` / edit (always include when `strength` key present).

Ensure cleanup still deletes the init file with the work dir.

- [ ] **Step 4: Run — expect PASS**

Run: `python -m unittest serve.test_images.EditRun -v`

---

### Task 4: HTTP route `POST /v1/images/edits` (JSON + multipart)

**Files:**
- Modify: `serve/server.py` (`_foreign_page`, `_post`, new `_images_edits`)
- Modify: `serve/fixtures/fake_sd_cli.py` only if argv parser breaks on `--strength` (it should already accept unknown `--flag value` pairs)
- Test: `serve/test_images.py`

**Interfaces:**
- Produces: handler that builds job via `parse_edit_request` + image decode, then same flow as `_images`
- Critical: branch **before** `req = json.loads(self._body() ...)` when path is `/v1/images/edits` and Content-Type is multipart

- [ ] **Step 1: Write failing HTTP tests**

```python
    def test_edits_json(self):
        ...  # as above against live server

    def test_edits_multipart(self):
        # urllib request with multipart body; assert 200 and strength in strata

    def test_edits_not_set_up(self):
        self.svc.images = None
        self.assertEqual(self.post_edits({...})[0], 404)

    def test_edits_missing_image_400(self):
        self.assertEqual(self.post_edits({"prompt": "x"})[0], 400)
```

- [ ] **Step 2: Run — expect FAIL** (404 not found / 415)

- [ ] **Step 3: Wire server**

1. In `_foreign_page`: if Content-Type starts with `multipart/form-data` **and** path will be edits — `_foreign_page` currently has no path. Options:
   - Change `_foreign_page` to accept optional `path` argument; allow `multipart/form-data` when `path == "/v1/images/edits"` and Origin is allowed.
   - Or allow multipart for any `/v1/` when Origin allowed (broader). Prefer **edits-only**.

Update call site:

```python
            if path.startswith("/v1/") and self._foreign_page(path):
                return
```

And inside `_foreign_page(self, path="")`:

```python
            ctype = self.headers.get("Content-Type", "")
            if ctype.startswith("application/json"):
                return False
            if path == "/v1/images/edits" and ctype.startswith("multipart/form-data"):
                return False
            self._json(415, {"error": {"message": "send application/json"}})
            return True
```

2. In `_post`, before the global JSON parse:

```python
            if path == "/v1/images/edits":
                self._images_edits()
                return
```

Implement `_images_edits`:

```python
        def _images_edits(self):
            gen = svc.images
            if gen is None:
                self._json(404, {"error": {"type": "invalid_request_error", "code": "images_not_set_up",
                                           "message": "image generation is not set up on this server (run setup "
                                                      "with --images qwen-image)"}})
                return
            ctype = self.headers.get("Content-Type", "")
            raw = self._body()
            try:
                if ctype.startswith("multipart/form-data"):
                    fields = images_api.parse_multipart_edits(raw, ctype)
                    image_bytes = fields.pop("image_bytes")
                    image_suffix = fields.pop("image_suffix")
                    job = images_api.coerce_edit_form(fields, gen.cfg)  # coerces strings → parse_edit_request
                else:
                    if not ctype.startswith("application/json"):
                        self._json(415, {"error": {"message": "send application/json or multipart/form-data"}})
                        return
                    req = json.loads(raw or b"{}")
                    if not isinstance(req, dict):
                        raise ValueError("send a JSON object")
                    image_bytes, image_suffix = images_api.decode_edit_image(req)
                    job = images_api.parse_edit_request(req, gen.cfg)
                job["image_bytes"] = image_bytes
                job["image_suffix"] = image_suffix
            except (images_api.ImageRequestError, ValueError, json.JSONDecodeError) as e:
                self._json(400, {"error": {"type": "invalid_request_error", "message": str(e)}})
                return
            # then same as _images: gpu_turn, gen.run, response
```

Keep error handling consistent with `_images` (500 on `ImageJobFailed`).

3. Update module docstring at top of `server.py` / `images.py` to mention edits.

- [ ] **Step 4: Run — expect PASS**

Run: `python -m unittest serve.test_images -v`  
Expected: all PASS (generations + edits)

---

### Task 5: Web UI — Image edit tab

**Files:**
- Modify: `serve/web/index.html`
- Modify: `serve/web/app.js`
- Modify: `serve/web/app.css` (only if needed for preview)

**Interfaces:**
- Tab id: `images-edit` (hash `#images-edit`)
- Button id: `tab-btn-images-edit`, panel `view-images-edit`
- Shown when `health.image_generation` is true (same as Images)

- [ ] **Step 1: Add markup**

In `index.html`, next to Images tab button:

```html
    <button class="st-tab" role="tab" id="tab-btn-images-edit" aria-controls="view-images-edit"
            aria-selected="false" data-tab="images-edit" hidden>
      ...<span>Image edit</span></button>
```

Panel: form with file input `#imge-file`, preview `#imge-preview`, prompt `#imge-prompt`, size `#imge-size`, seed `#imge-seed`, strength `#imge-strength` (number 0–1 step 0.05, value 0.75), submit `#imge-go`, hint `#imge-hint`, results `#imge-results`.

- [ ] **Step 2: Wire `app.js`**

- Extend `showTab` allowed names: include `images-edit`.
- On health: unhide `tab-btn-images-edit` with Images.
- On submit: `FormData` with `image`, `prompt`, `size`, optional `seed`, optional `strength`, `response_format=b64_json`; `fetch("v1/images/edits", { method: "POST", headers: headers(/* no Content-Type — browser sets multipart boundary */), body: form })`.
- Important: `headers(true)` today sets `Content-Type: application/json` — use a variant that sets auth **without** forcing JSON Content-Type for this call.
- Reuse `imageBusy` / `paintLive` so Monitor shows busy during edits too.

- [ ] **Step 3: Manual smoke (no GPU required if server uses fake — optional)**

If a real server with images is running: upload a PNG, prompt, strength 0.4, confirm image returns. Otherwise rely on HTTP tests.

- [ ] **Step 4: Syntax check**

Run: `node --check serve/web/app.js`  
Expected: exit 0

---

### Task 6: Docs — IMAGES.md + portability files

**Files:**
- Modify: `docs/IMAGES.md`
- Create: `docs/work/images-edits-decisions.md`
- Create: `docs/work/images-edits-patch-map.md`

- [ ] **Step 1: Extend `docs/IMAGES.md`**

Add a section **Image edits** after Request fields:

- Endpoint `POST /v1/images/edits`
- Multipart: `image`, `prompt`, optional `strength` (0–1, default 0.75), same optional fields as generations (`size`, `n`, `seed`, `steps`, `response_format`, `background`)
- JSON: `images: [{ "image_url": "data:image/png;base64,..." }]`
- Web: **Image edit** tab
- Note: mask / instruction edit / ComfyUI not included

Include a curl multipart example and a JSON data-URL example.

- [ ] **Step 2: Write `docs/work/images-edits-decisions.md`**

Copy the decision table from the design spec; note optional `strength`; list non-goals; point to this plan and the design spec paths.

- [ ] **Step 3: Write `docs/work/images-edits-patch-map.md`**

For each touched file, list:

- Purpose of the change
- Search anchors (function/class names, route strings)
- How to re-apply on a newer Strata (order: images.py → tests → server.py → web → docs)
- Verify: `python -m unittest serve.test_images` and `node --check serve/web/app.js`

Include a short “conflict tips” note if upstream renames `_images` or the Images tab.

- [ ] **Step 4: Self-check docs**

Confirm no TBD placeholders; commands match actual test module name.

---

## Spec coverage checklist

| Spec requirement | Task |
| --- | --- |
| `POST /v1/images/edits` OpenAI-shaped | 4 |
| Multipart + JSON data URL | 2, 4 |
| Optional `strength` default 0.75 | 1 |
| `sd-cli --init-img` + `--strength` | 1, 3 |
| GPU turn / same errors as generations | 3, 4 |
| New Image edit tab | 5 |
| No mask / instruction edit / ComfyUI | Global constraints |
| Portability `.md` files | 6 |
| `docs/IMAGES.md` | 6 |
| Tests without GPU | 1–4 |

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-11-23-images-edits.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — run tasks in this session with checkpoints  

Which approach?
