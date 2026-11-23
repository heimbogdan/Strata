# Image generation and edit

This page is for people who want Strata's server to make images through `POST /v1/images/generations` (Turbo) and
edit them through `POST /v1/images/edits` (Edit-2511), OpenAI's images API. Both are optional, off unless you ask,
and separate from reading pictures in chat (for that, use `strata launch --vision on` with a supported model and
reader).

It needs a [source checkout](SOURCE_INSTALL.md) and build tools. The steps below are not part of a normal app install.

The model is [Qwen-Image-2.1-Turbo](https://huggingface.co/Qwen/Qwen-Image-2.1-Turbo) (8 steps, CFG 1) in
[Unsloth's GGUF quants](https://huggingface.co/unsloth/Qwen-Image-2.1-Turbo-GGUF), run by
[stable-diffusion.cpp](https://github.com/leejet/stable-diffusion.cpp) (`sd-cli`), which setup compiles for your GPU.
It is under the **Qwen Research License**, not Apache 2.0. Read
[its license](https://huggingface.co/Qwen/Qwen-Image-2.1-Turbo/blob/main/LICENSE) before you use the images
commercially.

## Quick start

```sh
./setup.sh --setup --images qwen-image          # Linux
START-HERE.bat --setup --images qwen-image      # Windows
```

For an install that is already set up, without running the whole setup again:

```sh
.venv/bin/python tools/image/install.py --config strata-<model>.json
```

Then request an image:

```sh
curl http://127.0.0.1:8080/v1/images/generations -H "Content-Type: application/json" \
  -d '{"prompt": "a cartoon sloth mascot waving, flat vector illustration", "size": "1024x1024", "seed": 42}'
```

## What setup does

Setup compiles `sd-cli` (stable-diffusion.cpp at a pinned commit) into `engine-image/`, downloads three files into the
data folder's `models/qwen-image-2.1-turbo/`, checks each against its SHA-256 and writes an `"images"` section into the
model's run config.

| Piece | File | Size |
| --- | --- | --- |
| Denoiser, chosen by GPU memory | `qwen-image-2.1-turbo-Q4_K_M.gguf` up to 8 GB, `Q6_K` up to 12 GB, `Q8_0` above | 4.2 / 6.3 / 7.6 GB |
| Text encoder | `Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf` | 5.1 GB |
| VAE | `qwen_image_2.1_vae_bf16.safetensors` | 0.7 GB |

### Setup options

| Option | Effect |
| --- | --- |
| `--image-quant Q4_K_M\|Q6_K\|Q8_0` | Picks the denoiser. A bigger one than recommended is kept, with a warning. |
| `--image-backend cuda\|hip\|vulkan\|cpu` | Picks the backend. |
| `--image-gpu-policy auto\|keep\|shrink\|unload` | Sets `images.gpu_policy` ([below](#sharing-the-gpu-with-the-text-model)). |
| `--images no` | Takes the section out of the config. |

### Backends

| Backend | Used for |
| --- | --- |
| CUDA | NVIDIA. Needs the CUDA Toolkit. |
| HIP | AMD cards with their own memory, on Linux, with the same ROCm as the engine. |
| Vulkan | AMD APUs and iGPUs (Radeon 780M, Strix Point and Halo), Intel Arc, and AMD under Windows. |
| CPU | Fallback. |

A Linux PC without the Vulkan development files gets the LunarG Vulkan SDK unpacked into `third_party/` (no sudo). On
Windows, install the Vulkan SDK first. On Vulkan, setup adds `--vae-tiling --vae-tile-overlap 0.25`. An untiled
1024x1024 VAE decode on a Radeon 780M is one GPU job long enough to trip the kernel driver's job timeout, and the
quarter overlap decodes in half the time of sd.cpp's default half overlap.

## Request fields

| Field | Meaning |
| --- | --- |
| `prompt` | The description (required). |
| `size` | `WIDTHxHEIGHT`, each side a multiple of 32 from 256 to 2048 (`max_side`). Default and `auto`: `1024x1024`. |
| `n` | Images, 1 to 4 (`max_n`). Image *i* uses seed + *i*. |
| `response_format` | `b64_json` (default) or `url` (`/v1/images/files/<random name>.png`; the server keeps the newest 64). |
| `seed` | Strata's: a whole number for a repeatable image. Default: random; the answer says which. |
| `steps` | Strata's: 8 (Turbo's schedule). Another count uses stable-diffusion.cpp's own schedule, which Turbo was not made for. |
| `background` | `auto` (default) or `opaque`: the picture on white, as an 8-bit RGB PNG. `transparent`: the model's own transparency kept (an RGBA PNG). |

The answer has OpenAI's shape (`created`, `data[].b64_json` or `data[].url`, `revised_prompt` = the prompt,
`background`) plus `data[].seed` and a `strata` object with the seconds, steps, backend and `flatten_s` (the time
spent putting the picture on white). The settings are the model card's for stable-diffusion.cpp: 8 steps, CFG 1, euler,
Turbo's own sigmas, `--diffusion-fa`. The model can leave parts of a picture transparent; the API puts the picture on
white and returns an 8-bit RGB PNG, with the PNG's text chunk (prompt and settings) unchanged. With
`"background": "transparent"` you get the PNG exactly as plain `sd-cli` writes it, transparent areas included.

## Image edits (Qwen-Image-Edit-2511)

Instruction edit uses a **separate** model from Turbo generations:
[Qwen-Image-Edit-2511](https://huggingface.co/Qwen/Qwen-Image-Edit-2511) (Apache 2.0). Send a source picture and a
prompt to `POST /v1/images/edits`. The server runs `sd-cli` with `--ref-image`, `--llm_vision` and
`qwen_image_zero_cond_t=true` (20 steps, CFG 2.5, `--flow-shift 3`). There is no `strength` control: the model
follows the instruction while keeping the rest of the picture.

This route does **not** do masks or ComfyUI. Those are planned separately.

### Install edit models

Needs the same `sd-cli` as generations (run `tools/image/install.py` first, or omit `--reuse-exe` to compile):

```sh
.venv/bin/python tools/image/install_edit.py --config strata-<model>.json --reuse-exe
```

That downloads four files into the data folder's `models/qwen-image-edit-2511/` and writes an `"images_edit"`
section into the run config. Restart the server afterwards. Default quant: Q4_K_M up to 16 GB GPU memory, Q8_0 above.

| Piece | File | Size |
| --- | --- | --- |
| Denoiser | `qwen-image-edit-2511-Q4_K_M.gguf` (or Q8_0) | ~12.0 / ~20.8 GB |
| Text encoder | `Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf` | ~4.4 GB |
| Vision tower | `mmproj-F16.gguf` | ~1.3 GB |
| VAE | `qwen_image_vae.safetensors` | ~0.2 GB |

### Edit fields

| Field | Meaning |
| --- | --- |
| `image` | The source file (multipart only). PNG, JPEG, or WebP. |
| `prompt` | What to change (required). Same limits as generations. Prefer clear English instructions. |
| `size`, `n`, `response_format`, `background`, `seed`, `steps` | Same as [Request fields](#request-fields); default steps for edits: **20**. |

In JSON, put the source in OpenAI's edits shape instead of `image`:

| Field | Meaning |
| --- | --- |
| `images` | A list with **one** object: `{ "image_url": "data:image/png;base64,..." }`. Only **data URLs** are accepted (no `https://` fetch, no `file_id`). PNG, JPEG, or WebP. |

The answer matches generations (`model` is `qwen-image-edit-2511`).

### Examples

Multipart (typical for scripts and the web page):

```sh
curl http://127.0.0.1:8080/v1/images/edits \
  -F "image=@photo.png" \
  -F "prompt=change the jacket to a red coat, keep the face and background" \
  -F "size=1024x1024"
```

JSON with a data URL (handy when the picture is already in memory):

```sh
curl http://127.0.0.1:8080/v1/images/edits -H "Content-Type: application/json" \
  -d '{"images":[{"image_url":"data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="}],
       "prompt":"turn the sky orange at sunset","size":"1024x1024"}'
```

### Web UI

When image edit is set up (`images_edit` in the config), the server page shows an **Image edit** tab. Upload a file,
describe the change, set size and seed if you want. The page sends multipart to `POST /v1/images/edits`.

## Sharing the GPU with the text model

One job runs at a time. An image job takes the same turn a chat request takes, so a chat request waits for the image
and the other way round. The config's `images.gpu_policy` decides what the text model does meanwhile.

| Policy | The text model during an image job |
| --- | --- |
| `auto` (default) | `keep` when the image job fits next to it (an APU always), else `shrink` when the engine was started with `--vram-elastic`, else `unload`. |
| `keep` | Stays loaded and idle. |
| `shrink` | Gives VRAM from its expert cache (as `POST /v1/vram`) and takes it back afterwards. The conversation stays. |
| `unload` | Its conversation is saved to a file and the engine is stopped. The next start restores the conversation. `"reload": "eager"` starts it again right after the image; the default `lazy` starts it with the next chat request. |

Each image runs its own `sd-cli` process, so no image memory stays on the GPU between images. Loading the three files
takes a few seconds per image from the page cache.

## History / older measurements

> **Measured on:** seconds per image through the API, Q8_0, 8 steps, one `sd-cli` process per image with loading
> included. Strata version not recorded.

| GPU | Backend | 1024x1024 | 512x512 |
| --- | --- | --- | --- |
| RTX A4000 16 GB | CUDA | 27 s | 8.8 s |
| Radeon 780M (iGPU) | HIP | 131 s | 29 s |
| Radeon 780M (iGPU) | Vulkan | 179 s | 43 s |

On the 780M, HIP is faster but runs through the ROCm path whose queue evictions reset this GPU on the firmware tested
(a driver or firmware defect, not this feature; no reset was seen in these image runs). Vulkan is setup's default
there. `--image-backend hip` picks HIP.
