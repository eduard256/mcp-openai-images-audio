# gpt-image-2 prompting guide

This is the full, authoritative guide for the `image` tool. Read it
once per conversation, before your first call to `image`. It
distills OpenAI's official cookbook plus production patterns that
work reliably in 2026.

The guide is organized as a checklist you can follow top-to-bottom
when constructing any prompt.

---

## 1. Three modes of the `image` tool

The tool dispatches to one of two OpenAI endpoints based on the
`references_paths` parameter:

| `references_paths`        | Mode       | Endpoint                  |
|---------------------------|------------|---------------------------|
| omitted / empty list      | generate   | /v1/images/generations    |
| 1 absolute path           | edit       | /v1/images/edits          |
| 2..16 absolute paths      | compose    | /v1/images/edits          |

The model is the same in all three modes. The difference is only
whether it sees other images alongside your prompt.

---

## 2. Universal prompt structure

Write prompts in this order. For complex prompts, use line breaks
or labeled segments rather than one dense paragraph.

1. **Medium** — explicit: photo, watercolor, 3D render, vector,
   children's book illustration, ink sketch, oil painting, UI mockup.
2. **Subject + action** — who/what, doing what.
3. **Scene/background** — where, when (time of day), environmental
   conditions.
4. **Composition** — framing, viewpoint, lens, perspective.
5. **Lighting & mood** — direction, quality, atmosphere.
6. **Texture & detail** — materials, surface qualities, imperfections.
7. **Constraints** — what to preserve, what to exclude, things that
   must NOT appear.

The model weights the first ~50 words most heavily, so put the
medium and subject up front, not at the end.

---

## 3. Photorealism rules

gpt-image-2 responds well to **photography language**, not to vague
"quality cues". Use the words a photographer would use to describe
the shot, not the words a stock-photo SEO tag would use.

### USE these phrasings:
- `35mm film photograph`, `documentary still`, `candid shot`,
  `iPhone photo` — sets the medium
- `50mm lens`, `35mm lens`, `85mm portrait lens`,
  `shallow depth of field`, `medium close-up`, `eye-level`,
  `low angle` — composition cues
- `golden hour sunlight`, `overcast soft daylight`,
  `harsh midday sun`, `window backlight from the left`,
  `street lamp at night` — lighting cues
- `visible skin pores`, `fine wrinkles`, `freckles`, `peach fuzz`,
  `worn fabric`, `creased leather`, `weathered wood`, `dust on surface`,
  `subtle film grain`, `minor lens flare` — texture cues
- `candid`, `unposed`, `caught mid-action`, `slightly off-center`,
  `everyday detail`, `mundane background` — anti-idealization cues

### AVOID these (they push toward fake CGI gloss):
- `8K`, `4K`, `ultra-detailed`, `masterpiece`, `award-winning`
- `beautiful`, `stunning`, `glamorous`, `flawless skin`,
  `perfectly symmetric`
- `studio quality`, `professional retouch`, `cinematic grading`,
  `vibrant colors` (unless that's literally what you want)

### Add the trigger word when you really mean it
Including the literal word `photorealistic` or `real photograph`
near the start of the prompt strongly engages the model's photo
mode. Use it when you want a photo, omit it when you want art.

### Example: bad → good

Bad:
```
beautiful woman, 8K, ultra-detailed, masterpiece, studio lighting
```

Good:
```
Candid 35mm film photograph. A woman in her 40s laughing while
reading a book at a café table. Soft window backlight from the
left, late afternoon. Medium close-up, 50mm lens, shallow depth
of field. Visible skin pores, fine smile lines, slightly messy
hair. Subtle film grain, muted natural colors. Unposed, caught
mid-laugh. Background is a slightly out-of-focus café interior
with empty cups and a newspaper.
```

---

## 4. Text rendering inside images

gpt-image-2 reaches >95% accuracy on rendered text when prompted
deliberately. Without explicit instructions it often mis-spells.

Rules:

- Put the literal copy in **double quotes** in the prompt.
- Add the constraint `Include ONLY this text (verbatim): "..."` —
  this prevents the model from inventing extra words.
- Specify typography: `bold sans-serif`, `condensed serif`,
  `monospace`, font weight, color, placement.
- For tricky brand names, spell them letter-by-letter.
- For very text-heavy outputs (infographics, UI, posters), pass
  `quality: "high"` — text legibility scales with quality.
- For UI mockups, prefer `size: "3840x2160"` (4K) so individual
  characters render at >12 pixel-em.

Example:
```
Realistic billboard mockup of shampoo on a highway at sunset.
Billboard text (EXACT, verbatim): "Fresh and clean".
Typography: bold sans-serif, high contrast, centered, clean
kerning. Text appears once, perfectly legible. No watermarks,
no extra text.
```

---

## 5. Illustration and art styles

When you want art, explicitly name the medium and its handling.

- **Watercolor**: soft outlines, fluid edges, paper texture visible.
- **Hand-painted / oil**: visible brushstrokes, organic variation,
  canvas texture.
- **Vector / flat**: clean shapes, minimal strokes, no gradients,
  uniform color fills.
- **3D render**: octane / blender render, soft shadows,
  subsurface scattering for skin.
- **Children's book**: gentle palette, exaggerated proportions
  (oversized head), warm earthy colors.
- **Ink sketch**: pen-on-paper, hatching, no color or muted wash.

Style is non-sticky across iterations — restate it on each new
prompt rather than relying on continuity.

---

## 6. Edit mode (1 reference)

When you pass exactly one image to `references_paths`, the model
treats it as the source to modify. Tell it what to change AND what
to preserve — without the second part, the model often "improves"
things you wanted left alone.

Examples:

```
Remove the white background completely. Keep the apple identical
in shape, color, lighting, and shadow. Result on a fully
transparent background.
```

```
Make this scene look like a winter evening with snowfall. Use
input_fidelity="high" so geometry and composition are preserved.
Change ONLY environmental conditions — lighting, atmosphere,
precipitation, ground wetness.
```

```
Replace the woman's red dress with a fitted navy-blue blazer and
white shirt. Do not change her face, hair, body shape, pose, or
the background. Lighting and shadows must match the original.
```

For human/face edits, **always** pass `input_fidelity: "high"` —
otherwise faces drift across iterations. The cost increase is
small (~15% of input tokens).

---

## 7. Compose mode (2..16 references)

When you pass multiple references, the model can confuse which
input is the "subject" and which is the "style guide". You MUST
label every input by role inside the prompt.

Pattern:
```
Image 1: <role>. Image 2: <role>. ... Image N: <role>.
<Then the action: generate / compose / blend ...>
```

Common role labels:
- `subject` — the thing being depicted
- `style reference` — color palette, brushwork, mood
- `composition reference` — framing, layout, perspective
- `lighting reference` — light direction and quality
- `background` — the scene to place the subject into
- `clothing` / `product` — to be added to a person/scene

Examples:

```
Image 1: subject (the dog).
Image 2: style reference (oil painting, Van Gogh).
Render Image 1's content in the painterly style of Image 2.
Preserve the dog's recognizable identity.
```

```
Image 1: product (a perfume bottle).
Image 2: scene (a marble bathroom counter).
Place the product naturally on the counter in Image 2. Match the
lighting direction, color temperature, and shadow softness of
Image 2. Do not add or remove any other objects.
```

```
Image 1: person (full body).
Image 2: clothing (a wool coat).
Dress the person from Image 1 in the coat from Image 2. Do not
change face, hair, body shape, pose, or background. Match the
lighting and shadows of Image 1.
```
With `input_fidelity: "high"` for any edit involving a real person.

---

## 8. Picking `size` for the use case

`size` is required and has no default. Choose deliberately:

| Use case                                  | Recommended size |
|-------------------------------------------|------------------|
| Avatar, icon, single subject              | 1024x1024        |
| Landscape composition                     | 1536x1024        |
| Portrait composition (vertical)           | 1024x1536        |
| Hero block, album art (high-res square)   | 2048x2048        |
| 16:9 banner, video thumbnail              | 2048x1152        |
| 9:16 story / mobile portrait              | 1152x2048        |
| 4K UI mockup with readable text           | 3840x2160        |
| 4K vertical poster / mobile mockup        | 2160x3840        |

Cost scales roughly linearly with output token count, which
scales with output area. 4K is ~4× the price of 2048×1152.
Don't reach for 4K unless legibility actually demands it.

---

## 9. Quality and fidelity — when to set them

### `quality`
- **Omit (default)** — the auto setting picks high for most cases
  and produces excellent quality. This is the right choice 90% of
  the time.
- `low` — only for rapid drafts, brainstorming, throwaway batches.
  ~$0.006 per 1024×1024.
- `medium` — useful when generating many illustrations at once
  for a blog or feed. ~$0.05 per 1024×1024.
- `high` — explicitly request when text legibility is critical
  (UI mockups, posters, infographics) or when photorealism must be
  flawless. ~$0.21 per 1024×1024.

### `input_fidelity`
Only meaningful in edit/compose mode (when references_paths is
non-empty). Omit by default.

Pass `"high"` when:
- editing photos of real people (faces must be preserved),
- virtual try-on (clothing on a person),
- product placement where the product must look identical,
- any scenario where identity drift would be a bug.

---

## 10. Background

- `auto` (default) — let the model decide. Fine for most photos,
  illustrations, scenes.
- `transparent` — for logos, icons, isolated products, or anything
  you'll composite later. Requires `.png` or `.webp` output.
- `opaque` — explicitly force a solid background even when the
  prompt would otherwise produce transparency.

### Important: model routing for `transparent`

gpt-image-2 currently REJECTS `background='transparent'`
(documented regression with no announced fix). To keep transparency
working end-to-end, this server **automatically routes transparent
requests to gpt-image-1.5**, which still supports alpha. You don't
need to do anything — just set `background='transparent'` and the
server picks the right model. The response field `model` will read
`gpt-image-1.5` for those calls and `gpt-image-2` for everything
else.

Practical consequence: image quality on transparent calls is
gpt-image-1.5 quality, not the gpt-image-2 flagship. If a request
is sensitive to maximum quality AND needs transparency, generate
with `background='auto'` on gpt-image-2 and remove the background
with a downstream tool (cwebp, magick, a remove-bg utility).

### CRITICAL: never try to "ask for transparency" in the prompt

If you cannot pass `background='transparent'` for some reason and
you write things like *"on a fully transparent background"* or
*"alpha channel"* in the prompt, the model will sometimes paint
the universal **gray checkerboard pattern** (the visual symbol of
transparency in editors) into the RGB pixels of the image. The
result *looks* transparent in a thumbnail viewer but is actually
opaque pixels — completely unusable as a transparent asset.

The server detects this trap and surfaces a warning in the tool
response (`alpha_appears_baked: true`). If you see that flag, the
output is a fake. Regenerate with `background='transparent'` (so
the server routes you to gpt-image-1.5), or accept an opaque
output and remove the background downstream.

Combining `transparent` with a `.jpg`/`.jpeg` output_path is
rejected by the tool (JPEG has no alpha channel).

---

## 11. Output format

The tool picks the format from the `output_path` extension:

| Extension       | Format | Notes                                |
|-----------------|--------|--------------------------------------|
| `.png`          | PNG    | Lossless, supports transparency.     |
| `.webp`         | WebP   | Modern web. Smaller, supports alpha. |
| `.jpg` / `.jpeg`| JPEG   | Smaller, no transparency.            |

Don't pass an `output_format` parameter — it doesn't exist; the
extension is the source of truth.

---

## 12. Iteration discipline

When iterating:

- Make ONE change per iteration. Don't rewrite the whole prompt.
- Re-state critical style cues on every follow-up — they don't
  carry over.
- For identity-preserving edits, repeat the "do not change face,
  hair, body shape, pose" lock on every iteration.
- If the model drifts away from a style after 2-3 prompts, drop
  back to the original prompt and apply the new change to it
  rather than chaining edits.

---

## 13. Anti-patterns — checklist

Before you submit a prompt, scan it for these red flags:

- [ ] One dense paragraph mixing scene + subject + style + constraints
      → split into ordered segments
- [ ] Generic quality tags (`8K`, `masterpiece`, `award-winning`)
      → replace with photography language
- [ ] No medium specified (`a cat`)
      → name the medium (`watercolor of a cat`)
- [ ] Multi-image prompt with no role labels
      → add `Image 1: ..., Image 2: ...`
- [ ] Identity-preserving edit without `input_fidelity: "high"`
      → set it
- [ ] `transparent` with a `.jpg` output_path
      → use `.png` or `.webp`
- [ ] Trying to get transparency by writing it in the prompt
      → set `background='transparent'`; words alone invite the
        gray-checkerboard trap (section 10)
- [ ] Tool response shows `alpha_appears_baked: true`
      → the image is a fake; regenerate or post-process
- [ ] `size` left to chance
      → consult the table in section 8

---

## 14. Concrete example prompts

### Photoreal portrait
```
Candid 35mm film photograph. An elderly fisherman repairing a
net on the deck of a small wooden boat. Late afternoon coastal
sunlight from the left. Medium close-up, 50mm lens, shallow
depth of field. Visible skin texture: weathered wrinkles, sun
spots, faded sailor tattoos on the forearm. Worn wool sweater
with frayed cuffs. Subtle film grain, honest natural color, no
retouching. Background slightly out of focus: ocean horizon,
empty fish crates.
```

### UI mockup with readable text (4K)
```
High-fidelity UI design mockup. Modern web application called
"PhotoVault" — a photo-sharing platform with Instagram-like
visual language: rounded cards, soft shadows, generous
whitespace, friendly Inter typography.
Top nav: logo on the left, search bar with placeholder "Search
photos, people, places", user avatar on the right.
Center: vertical feed of three photo posts, each with circular
avatar, username @example_user, photo, caption, like/comment
icons.
Right sidebar: "Suggested" with four user cards, each with
Follow button.
Light theme, warm white background. Card corner radius 16px,
subtle drop shadows. Typography hierarchy clear. All readable
text rendered crisply, no gibberish letters. Treat as a shipped
product screenshot, not a wireframe.
```
Pair with `size: "3840x2160"`, `quality: "high"`.

### Logo with transparency
```
Original logo for a bakery called "Field & Flour". Warm,
simple, timeless. Clean vector shapes, a stalk of wheat
intertwined with a sourdough loaf silhouette. Flat design,
minimal strokes, two-tone palette: deep amber on dark warm
brown. Centered, generous padding, balanced negative space.
No watermark, no extra text outside the wordmark.
```
Pair with `size: "1024x1024"`, `background: "transparent"`,
`output_path` ending in `.png`. The server will route this to
gpt-image-1.5 automatically; the response will reflect that in
the `model` field. Do NOT mention "transparent background" in
the prompt itself — the parameter does the work; words in the
prompt invite the checkerboard trap (section 10).

### Compose: product on a scene
```
Image 1: product (a ceramic coffee mug, isolated on white).
Image 2: scene (a wooden kitchen counter with a window in the
background, morning light).
Place the product naturally on the counter from Image 2,
slightly off-center to the right. Match the warm morning light
and direction of shadows from Image 2. Add a faint reflection
of the mug on the wood surface. Do not add other objects.
```

### Background swap with identity lock
```
Replace the background with a quiet park at golden hour, soft
backlight through trees. Do not change the subject's face,
expression, hairstyle, body shape, pose, or clothing in any
way. Preserve exact identity. Match the new lighting on the
subject so they look like they were photographed in the new
environment.
```
With `input_fidelity: "high"`.
