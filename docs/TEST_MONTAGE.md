# Real-gameplay cinematic test

This is a mechanics/evaluation sample, not a claim of Kaiser-level artistry or a personal gameplay edit.
The renderer is the same create_montage pipeline used by the desktop, without live Ollama inference.

## Source credits

- **Xonotic 0-8-2 gameplay**, Drummyfish and Xonotic developers (2019), GPL-3.0-or-later.
  Source/author/license: https://commons.wikimedia.org/wiki/File:Xonotic_0-8-2_gameplay.webm
  Original: https://upload.wikimedia.org/wikipedia/commons/b/b9/Xonotic_0-8-2_gameplay.webm
  Game source: https://gitlab.com/xonotic/xonotic
  License: https://www.gnu.org/licenses/gpl-3.0.html
- **Amazing Grace**, United States Marine Band and Gunnery Sgt. Sara Sheffield; arrangement
  Capt. Ryan J. Nowlin; lyrics John Newton, traditional tune. Performance recorded in 2016.
  Wikimedia lists the recording, arrangement and composition as public domain in the US.
  Source: https://commons.wikimedia.org/wiki/File:Amazing_Grace_US_Marine_Band.ogg
  Original: https://upload.wikimedia.org/wikipedia/commons/2/21/Amazing_Grace_US_Marine_Band.ogg

No endorsement by any source creator is implied. The sample is an edited derivative:
source segments selected/reordered, retimed, resized and zoomed; music excerpt mixed/mastered;
original closing text added. The video derivative is distributed under GPL-3.0-or-later.
The reproduction package supplies original media, transformation recipe, timelines and license.
This applies to the sample, not a change to the editor repository's software license.

## Reproduction

Install the editor and FFmpeg. Download the two originals into an asset directory outside Git.
Run `python examples/render_gameplay_test.py --assets /path/to/assets --output /path/to/test.mp4`.
The recipe refuses to overwrite prepared media. On repeat, choose a fresh directory.

The recipe prepares video seconds 20–130, music seconds 30–58, then requests a 24-second
720p/30fps edit with the cinematic profile: .10 gameplay gain, .9 music gain, measured audio
mastering, .24-second zoom decay and “Walk with Christ. Let grace lead the way.” closing title.
The timeline/analysis/validation sidecars provide actual decisions rather than a hand-crafted
sequence disguised as automatic editing. Original source files and renders are excluded from Git.
