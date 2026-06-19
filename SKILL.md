---
name: image2-gen-skill
description: Generate images from text prompts and edit/generate images from reference images through a gpt-image-2 OpenAI-compatible image API. Use when the user asks to 生图, 生成图片, 生成一张图, 画图, 文生图, text-to-image, image generation, 图生图, 改图, 修图, 图片编辑, image-to-image, or edit a reference image. Use when Codex needs to call text-to-image `/v1/images/generations`, image-edit `/v1/images/edits`, save returned image URLs or base64 images, time image API calls, or automate the workflows shown in the bundled HTML test pages.
---

# Image2 Gen Skill

Use this skill to create images from text or create edited images from a reference image using the API shape in the bundled HTML test pages.

## First Checks

1. Check that `~/.config/image2-gen/config.json` exists or that credentials were passed explicitly.
   - Preferred config: `{"baseurl":"https://your-image-api.example.com/v1","token":"<api-token>","model":"gpt-image-2"}`
   - `baseurl` includes the API version prefix, for example `/v1`. The scripts append `/images/generations` or `/images/edits`.
   - `token` is used as `Authorization: Bearer <token>`.
   - `model` is optional. It defaults to `gpt-image-2` when omitted. The scripts only support `gpt-image-2`.
   - `--baseurl`, `--endpoint`, and `--api-key`/`--token` can override config values for one run.
2. Resolve the image model: command-line `--model`, then config `model`, then `gpt-image-2`.
3. For image editing, check that the input image exists and is a PNG, JPEG, or WebP file.
4. Prefer saving outputs into a user-visible output directory. If none is specified, use `image2_outputs/`.

## Prompt Preprocessing

Before execution, act as a professional AI image prompt optimization expert:

1. First identify the drawing mode: text-to-image when no reference image is provided, or image-to-image when one or more reference images are provided.
2. Fully preserve the user's specified subject, action, scene, atmosphere, style, composition, and special requirements. Do not delete, replace, or change the original intent.
3. Enrich the prompt with professional visual dimensions: camera composition, lighting, material texture, clarity/detail level, rendering feel, color palette, tone, and atmosphere.
4. Internally create concise avoidance constraints: avoid malformed facial features, extra hands or feet, missing limbs, low-resolution blur, watermark text, distortion, noise, color fringing, cluttered background, and broken art style.
5. Keep the positive prompt at or below 750 Chinese characters and avoidance constraints at or below 300 Chinese characters. Remove redundant modifiers when too long.
6. User-provided parameters override automatic recommendations. Extract explicit size, count, quality, output format, background, compression, moderation, image paths, and mask paths from the user request when present.
7. Internally organize the plan as positive prompt, negative/avoidance constraints, and GenParams. Do not separately output this three-part plan unless the user asks to see the optimized prompt.
8. When executing, map only parameters supported by the `gpt-image-2` scripts: `--size`, `--count`, `--quality`, `--background`, `--output-format`, `--output-compression`, `--moderation`, `--user`, and for edits `--image`/`--mask`.
9. Treat `steps`, `cfg`, `denoising`, and `style` as internal reference values only. Do not pass them as script parameters.
10. Because `gpt-image-2` has no separate negative prompt field, merge concise avoidance constraints into the final `--prompt` only when they materially help the request.

Text-to-image mode:

- Use internal `denoising=0.0`.
- Automatically choose sensible size, quality, and visual style when the user did not specify them.
- Focus enrichment on scene environment, camera viewpoint, lighting, scale, and atmosphere.

Image-to-image mode:

- Estimate internal denoising by edit strength: minor retouch `0.3-0.4`, portrait/photo preservation `0.5-0.6`, creative transformation `0.7-0.8`.
- Add preservation language to the prompt: preserve the source image's base structure, subject silhouette, character outline, and main composition.
- Add image-to-image avoidance constraints when useful: avoid major composition changes, broken face shape, and completely detaching from the source image structure.

Defect-feedback mode:

- If the user reports defects such as a dark image, malformed hands, messy background, blur, bad face, or color problems, only correct the defect-related descriptions.
- Preserve the original subject, composition, and intent, and add matching avoidance constraints for the reported defect.

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
  --quality high \
  --background auto \
  --output-format png \
  --output-dir image2_outputs
```

### Image edit / image to image

Use `scripts/edit_image.py`.

```bash
python scripts/edit_image.py --prompt "<prompt>" --image <path-to-image>
```

Defaults:

- Endpoint: `<baseurl>/images/edits`
- Multipart image field: `image[]`
- Size: `auto`
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
  --size 1024x1536 \
  --count 1 \
  --quality high \
  --background auto \
  --output-format png \
  --output-dir image2_outputs
```

## API Shape

Text-to-image sends JSON:

- Headers: `Authorization: Bearer <key>`, `Content-Type: application/json`
- Body: `model`, `prompt`, `size`, `n`, `quality`, `background`, `output_format`, `moderation`, optional `output_compression`, optional `user`.

Image edit sends `multipart/form-data`:

- Headers: `Authorization: Bearer <key>`
- Fields: `image[]`, optional `mask`, `model`, `prompt`, `size`, `n`, `quality`, `background`, `output_format`, `moderation`, optional `output_compression`, optional `user`.

Both scripts accept responses containing `data[].url` or `data[].b64_json`. They save images, save `response.json`, and print elapsed time.

## Failure Handling

- If the request fails, read the saved/printed JSON error first.
- If browser HTML tests fail with CORS but scripts work, treat the Python script result as the API truth; the browser may be blocked by cross-origin response headers.
- Do not log full API keys. The scripts only print request summaries with credentials omitted.
