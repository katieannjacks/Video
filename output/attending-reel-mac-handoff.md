# Attending reel: run on your Mac

## 1. Gather the files into one folder

Make a folder, for example `~/Movies/attending-reel/`, and put these in it:

From Google Drive (download the originals, not the chat uploads; the chat uploads were shrunk to 576x1024):
- `copy_62FF5FF2-EE15-4CA5-932C-5734303202A5.mov` (main 4-minute clip, about 465 MB)
- `copy_E6E762E2-5902-4B56-90CF-E535149E26F0.mov` (about 37 MB)
- `copy_D13A0472-E9B2-41ED-8B96-D1CD416014DF.mov` (about 31 MB)
- `IMG_4515.MOV` (about 52 MB, extra face take)

From Photos:
- The Attending screen recording. In Photos, select it, then File > Export > Export Unmodified Original, into the same folder.
- Any Attending screenshots you want considered for beats 4 and 5.

Before you hand it over, scrub the screen recording yourself. If it shows a patient name, client name, record number or clinic name, either re-record it with dummy data or plan to blur it.

## 2. One-time setup (Terminal)

```bash
brew install ffmpeg
```

```bash
python3 -m pip install --user faster-whisper
```

```bash
brew install --cask font-plus-jakarta-sans
```

If the font cask isn't found, download Plus Jakarta Sans from https://fonts.google.com/specimen/Plus+Jakarta+Sans and double-click the Bold .ttf to install it.

## 3. Start Claude Code in that folder

```bash
cd ~/Movies/attending-reel && claude
```

Then paste the prompt below.

---

## Prompt to paste

Edit a vertical Instagram/TikTok reel from the video clips, screen recording and screenshots in this folder. Do not modify or delete the originals; write everything to ./output.

Setup: ffmpeg/ffprobe, faster-whisper (model medium.en, word_timestamps=True, CPU int8 is fine) and the Plus Jakarta Sans Bold font should already be installed. Verify each; ask me before installing anything (Homebrew is fine). Cache each transcript as JSON in ./output/transcripts so nothing is re-transcribed.

Files: the main take is the ~4-minute copy_62FF5FF2...mov. copy_E6E762E2...mov, copy_D13A0472...mov and IMG_4515.MOV are extra takes. The Attending screen recording (exported from Photos) and any screenshots are B-roll for beats 4 and 5. iPhone .MOV files may carry rotation metadata and HDR (HLG/Dolby Vision); honor rotation and tone-map to SDR BT.709 so colors don't look washed out.

Steps:
1. ffprobe every file. Transcribe each face clip with word-level timestamps.
2. Match the transcripts to the SCRIPT below. For each line, pick the cleanest take across all clips, trim flubs, false starts and dead air (about 0.1 to 0.2 s padding, never cut inside a word, 30 ms audio fades at every cut to avoid pops).
3. Assemble in script order as 1080x1920, 30fps. Crop/scale face clips to fill 9:16.
4. During beat 4 (shows its work / citations) and beat 5 (dosing calculator), overlay the matching part of the screen recording (or a screenshot): full width, slow zoom-in, my face audio continues underneath. Pick the segment that best matches each line; ask me if unclear.
5. Burn in the ON-SCREEN TEXT for each beat in the top third, Plus Jakarta Sans Bold, white with a subtle dark shadow, max 2 lines.
6. Burn in word-synced captions from the transcript (2 to 4 words at a time) in the lower-middle, above the bottom 20% where app buttons sit. Highlight the active word in #F17650. Spell "Plumb's", "AAVSB" and "Attending by Instinct" correctly even if Whisper mishears them. Captions are applied last, after all overlays.
7. Normalize audio to about -14 LUFS (two-pass loudnorm, true peak -1 dBTP). Export H.264 MP4 to ./output/attending-reel-v1.mp4, plus ./output/captions.srt and ./output/edit-list.md listing which clip and timecodes were used for each beat.
8. Make a contact sheet of frames every 2 seconds (./output/contact-sheet.jpg). Flag any frame showing patient names, client info, record numbers or clinic details, and check every frame of the screen-recording overlays for the same.
Show me the edit list before the final render.

SCRIPT (beats):
1 Hook: This is Plumb's on steroids.
2 Who: I'm Dr. Katie Jackson, and I've been testing Attending by Instinct, from the team behind Plumb's. Quick disclosure: I got free early access as a preview tester. Nobody paid for this video.
3 AAVSB: Here's what the AAVSB says. Practice acts don't regulate the tools we use. They regulate how we use them. A scalpel isn't regulated. The use of it is.
4 Shows its work: And a lot of AI is a black box. It doesn't show its work. Attending shows its work. You can see exactly where the answer came from, and every answer cites its sources.
5 Dosing: On drug dosages, it walks you through the calculation and puts a calculator right in the chat. You can manually change the dose, play with the numbers, and see how you'd get a different output.
6 Your take: This isn't a ChatGPT wrapper. It's built only for licensed veterinarians. It's a big leg up in my day-to-day workflow, even just for double-checking my own work. You still have to use your own professional judgment. I'm still the vet.
7 CTA: There's a free 14-day trial if you want to try it. Would you use this on a busy shift? Tell me below.
(I may have ad-libbed. Follow what I actually said, using the script as a guide.)

ON-SCREEN TEXT:
1 PLUMB'S ON STEROIDS?
2 ATTENDING BY INSTINCT . FREE PREVIEW ACCESS, NOT SPONSORED
3 A SCALPEL ISN'T REGULATED. HOW YOU USE IT IS.
4 IT SHOWS ITS WORK
5 EDIT THE DOSE RIGHT IN THE CHAT
6 BUILT FOR LICENSED VETS . YOU'RE STILL THE VET
7 FREE 14-DAY TRIAL . WOULD YOU USE THIS?
