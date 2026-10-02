# UI assets

`src/montage_editor/resources/cathedral.jpg` is an original generated application backdrop, created using the built-in image-generation tool. It is package data, not a screenshot of the reference or external gameplay. The user-provided image was a style/composition reference only and is not committed.

Generation prompt: “Generate just the cinematic cathedral artwork, NO UI, NO TEXT, NO BUTTONS, NO LETTERS, no watermark. Wide panoramic monochrome gothic cathedral interior, ornate soaring arches and weathered angel statues at both sides, massive luminous white Christian cross centered deep in nave, mist, volumetric rays, tiny human silhouette for scale, polished black and silver tones, dramatic deep blacks. Similar atmospheric realism to the top cathedral hero in the reference. Preserve broad darker zones on either side of cross for overlay headings. Detailed high-end film matte painting. Wide landscape composition.”

`docs/ui-preview.png` is a screenshot of the actual desktop home layout without user footage, not an AI-generated screenshot. Regenerate using an offscreen QApplication and Studio.grab(). The home backdrop is decorative; it is not exported into gameplay montages automatically.

The October 2 refinement uses this image only at 7% opacity behind a graphite banner. Code-painted film frames and abstract viewfinder layers replace prominent religious imagery. Home copy is neutral; the optional story-tone and closing-line controls carry the faith direction. The screenshot records the actual refined empty workspace.


## 2026-10-02 redesign (user direction: primarily white, new font, new structure, more colour)

- Fonts: Manrope (UI) and Sora (display), static TTF weights downloaded from Google Fonts into
  `resources/fonts/`, each with its SIL Open Font License text (`OFL-manrope.txt`, `OFL-sora.txt`).
  Registered at runtime by `desktop.load_fonts()`; Qt falls back to system sans if they fail to load.
- Structure: top app bar (gradient brand mark, horizontal navigation, status chips) replaces the left
  rail; hero banner; "Start your edit" card (drop zone with the visible clip list, soundtrack picker,
  gradient Create button) beside the preview; full-width colour-coded timeline; Creative controls stay
  a side drawer. The previously hidden source-library panel is gone; its clip list now lives in the
  Create card.
- Colour: white canvas with violet (#6d4dff) → pink (#ff4f8b) primary accent, teal (#11b3a3) for music,
  amber (#ffad1f) for dialogue. The video surface stays black so footage is judged correctly. The
  cathedral art remains at 4% opacity as texture only. `resources/chevron.svg` is an original icon.
- `docs/ui-preview.png` was regenerated from the real offscreen app at 1520×1000.
