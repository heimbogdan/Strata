# Image Edit-2511 — patch map

Portability notes for re-applying instruction edit on top of Turbo generations.

## Re-apply order

1. `tools/image/qedit.py` — pinned HF files, `image_edit_config`
2. `tools/image/install_edit.py` — download + write `"images_edit"`
3. `serve/images.py` — `kind=="edit"` → `--ref-image`, `--llm_vision`, CFG 2.5, no strength
4. `serve/server.py` — `svc.images_edit`, health `image_edit_generation`, edits 404 `images_edit_not_set_up`
5. `serve/web/*` — edit tab gated on `image_edit_generation`; no Strength field
6. `serve/test_images.py` — `edit_cfg`, ref-image command tests
7. `docs/IMAGES.md` — install_edit + edit fields

## Verify

```sh
python -m serve.test_images
python tools/image/install_edit.py --print --quant Q4_K_M --backend vulkan --gpu-gb 16
```
