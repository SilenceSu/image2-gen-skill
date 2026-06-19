---
name: image2-gen-skill
description: Generate images from text prompts and edit/generate images from reference images through an OpenAI-compatible image API. Use when Codex needs to call text-to-image `/v1/images/generations`, image-edit `/v1/images/edits`, save returned image URLs or base64 images, time image API calls, or automate the workflows shown in the bundled HTML test pages.
---

# Image2 Gen Skill

Use this skill to create images from text or create edited images from a reference image using the API shape in the bundled HTML test pages.

## First Checks

1. Check that `~/.config/image2-gen/config.json` exists or that credentials were passed explicitly.
   - Preferred config: `{"baseurl":"https://your-image-api.example.com/v1","token":"<api-token>","model":"gpt-image-2"}`
   - `baseurl` includes the API version prefix, for example `/v1`. The scripts append `/images/generations` or `/images/edits`.
   - `token` is used as `Authorization: Bearer <token>`.
   - `model` is optional. It defaults to `gpt-image-2` when omitted.
   - `--baseurl`, `--endpoint`, and `--api-key`/`--token` can override config values for one run.
2. Resolve the image model: command-line `--model`, then config `model`, then `gpt-image-2`.
3. For image editing, check that the input image exists and is a PNG, JPEG, or WebP file.
4. Prefer saving outputs into a user-visible output directory. If none is specified, use `image2_outputs/`.

## Prompt Preprocessing

Before text-to-image or image-to-image execution, act as a professional text-to-image and image-to-image prompt engineer:

- Preserve every core subject, character, object, action, scene, and user constraint from the user's request.
- Add useful visual details for lighting, composition, camera/viewpoint, image quality, texture, atmosphere, and style.
- Optimize the prompt before execution, then send the optimized prompt to the script.
- Do not change the user's intent, replace the main subject, remove required elements, or add contradictory content.
- For image editing, explicitly preserve the source image's required subjects unless the user asks to replace or remove them.

## Workflows

### Text to image

Use `scripts/generate_image.py`.

```bash
python scripts/generate_image.py --prompt "<prompt>"
```

Defaults:

- Endpoint: `<baseurl>/images/generations`
- Size: `1024x1024`
- Count: `1`
- Response format: `url`
- Output directory: `image2_outputs/`

Useful options:

```bash
python scripts/generate_image.py \
  --api-key <key> \
  --baseurl https://your-image-api.example.com/v1 \
  --model <model> \
  --prompt "<prompt>" \
  --size 1536x1024 \
  --count 1 \
  --response-format b64_json \
  --extra-json '{"quality":"high","style":"vivid"}' \
  --output-dir image2_outputs
```

### Image edit / image to image

Use `scripts/edit_image.py`.

```bash
python scripts/edit_image.py --prompt "<prompt>" --image <path-to-image>
```

Defaults:

- Endpoint: `<baseurl>/images/edits`
- Multipart image field: `image`
- Size: `1024x1024`
- Count: `1`
- Output directory: `image2_outputs/`

Useful options:

```bash
python scripts/edit_image.py \
  --api-key <key> \
  --baseurl https://your-image-api.example.com/v1 \
  --model <model> \
  --prompt "<prompt>" \
  --image reference.png \
  --image-field-name image \
  --size 1024x1536 \
  --count 1 \
  --extra-json '{"quality":"high","response_format":"url"}' \
  --output-dir image2_outputs
```

## API Shape

Text-to-image sends JSON:

- Headers: `Authorization: Bearer <key>`, `Content-Type: application/json`
- Body: `model`, `prompt`, `size`, `n`, `response_format`, plus any `--extra-json` keys.

Image edit sends `multipart/form-data`:

- Headers: `Authorization: Bearer <key>`
- Fields: `<image-field-name>`, `model`, `prompt`, `size`, `n`, plus any `--extra-json` keys.

Both scripts accept responses containing `data[].url` or `data[].b64_json`. They save images, save `response.json`, and print elapsed time.

## Failure Handling

- If the request fails, read the saved/printed JSON error first.
- If browser HTML tests fail with CORS but scripts work, treat the Python script result as the API truth; the browser may be blocked by cross-origin response headers.
- Do not log full API keys. The scripts only print request summaries with credentials omitted.
