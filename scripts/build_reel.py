"""Build the Attending reel: cut segments, overlays, titles, captions, loudness."""
import json, os, subprocess, sys
from PIL import Image, ImageFont
import pillow_heif

pillow_heif.register_heif_opener()
ROOT = '/home/user/Video'
W = f'{ROOT}/output/work'
OUT = f'{ROOT}/output'
UP = '/root/.claude/uploads/042f5f85-045e-5caf-be01-2ca98b9235d6'
FONT = '/root/.fonts/PlusJakartaSans-Bold.ttf'
SRC = {
    'I': (f'{UP}/b52cbbc2-copy_D13A0472-E9B2-41ED-8B96-D1CD416014DF.mov', 'b52cbbc2-copy_D13A0472-E9B2-41ED-8B96-D1CD416014DF', 'Intro (copy_D13A0472)'),
    'M': (f'{ROOT}/source/main_62FF5FF2.mov', 'main_62FF5FF2', 'Main (copy_62FF5FF2)'),
    'O': (f'{UP}/51fa3bae-copy_E6E762E2-5902-4B56-90CF-E535149E26F0.mov', '51fa3bae-copy_E6E762E2-5902-4B56-90CF-E535149E26F0', 'Outro (copy_E6E762E2)'),
}
# beat, source, in, out
SEG = [
    (1, 'I', 2.25, 7.55), (1, 'I', 8.05, 12.98), (1, 'I', 13.70, 17.60), (1, 'I', 18.20, 22.30),
    (2, 'M', 5.28, 9.32), (2, 'M', 18.35, 21.80), (2, 'M', 22.68, 28.62), (2, 'M', 31.06, 33.40),
    (3, 'M', 35.72, 41.18), (3, 'M', 41.37, 46.25), (3, 'M', 48.65, 53.68),
    (4, 'M', 56.35, 60.30), (4, 'M', 60.70, 63.15), (4, 'M', 64.10, 65.20), (4, 'M', 67.95, 68.90),
    (4, 'M', 73.19, 76.00), (4, 'M', 76.55, 80.70),
    (5, 'M', 82.80, 87.55), (5, 'M', 88.30, 90.70), (5, 'M', 91.10, 98.15), (5, 'M', 98.50, 104.30), (5, 'M', 104.55, 105.50),
    (6, 'M', 107.00, 109.80), (6, 'M', 110.57, 113.70), (6, 'M', 228.10, 230.40), (6, 'M', 230.90, 232.45),
    (7, 'M', 235.03, 237.85), (7, 'O', 0.55, 11.95), (7, 'O', 13.70, 17.50),
]
TITLES = {
    1: ["PLUMB'S ON STEROIDS?"],
    2: ["ATTENDING BY INSTINCT", "FREE PREVIEW ACCESS, NOT SPONSORED"],
    3: ["A SCALPEL ISN'T REGULATED.", "HOW YOU USE IT IS."],
    4: ["IT SHOWS ITS WORK"],
    5: ["EDIT THE DOSE RIGHT IN THE CHAT"],
    6: ["BUILT FOR LICENSED VETS", "YOU'RE STILL THE VET"],
    7: ["FREE 14-DAY TRIAL", "WOULD YOU TRUST IT?"],
}
FIX = {  # (source, rounded start) -> replacement text ('' drops the word)
    ('M', 7.30): 'animal', ('M', 7.44): '', ('M', 108.6): 'ChatGPT', ('M', 89.9): "Plumb's",
}
GLOBAL_FIX = {'plums': "Plumb's", 'attending': 'Attending', 'instinct': 'Instinct', 'gbt': ''}


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print(r.stderr[-3000:]); sys.exit(1)
    return r


def stage_segments():
    os.makedirs(f'{W}/seg', exist_ok=True)
    lst = []
    for i, (b, s, a, e) in enumerate(SEG):
        path, _, _ = SRC[s]
        d = e - a
        out = f'{W}/seg/{i:02d}.mp4'
        lst.append(out)
        if os.path.exists(out): continue
        vf = 'scale=1080:1920:flags=lanczos,setsar=1,fps=30,format=yuv420p'
        af = f'aresample=48000,aformat=channel_layouts=stereo,afade=t=in:st=0:d=0.03,afade=t=out:st={d-0.03:.3f}:d=0.03'
        run(['ffmpeg', '-y', '-v', 'error', '-ss', f'{a}', '-i', path, '-t', f'{d:.3f}', '-map', '0:v:0', '-map', '0:a:0',
             '-vf', vf, '-af', af, '-c:v', 'libx264', '-preset', 'medium', '-crf', '16', '-c:a', 'aac', '-b:a', '256k', out])
    with open(f'{W}/concat.txt', 'w') as f:
        f.writelines(f"file '{p}'\n" for p in lst)
    run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', f'{W}/concat.txt', '-c', 'copy', f'{W}/base.mp4'])


def timeline():
    t, tl = 0.0, []
    for b, s, a, e in SEG:
        tl.append((t, t + e - a)); t += e - a
    return tl, t


def words_out():
    tl, _ = timeline()
    cache, ws = {}, []
    for (b, s, a, e), (t0, t1) in zip(SEG, tl):
        if s not in cache:
            cache[s] = json.load(open(f'{OUT}/transcripts/{SRC[s][1]}.json'))['words']
        for w in cache[s]:
            mid = (w['s'] + w['e']) / 2
            if not (a <= mid <= e): continue
            txt = w['w'].strip()
            key = (s, round(w['s'], 2))
            if key in FIX: txt = FIX[key]
            core = txt.strip('.,?!').lower()
            if core in GLOBAL_FIX:
                txt = GLOBAL_FIX[core] + txt[len(txt.rstrip('.,?!')):] if GLOBAL_FIX[core] else ''
            if not txt: continue
            st = max(w['s'], a) - a + t0
            en = min(w['e'], e) - a + t0
            if txt.startswith('-') and ws:  # rejoin "14" "-day"
                ws[-1]['w'] += txt; ws[-1]['e'] = en; continue
            ws.append({'w': txt, 's': st, 'e': en, 'beat': b})
    return ws


def words_final():
    """Words timed to the rendered reel (re-transcribed), with spelling fixes."""
    tl, _ = timeline()
    raw = []
    for k, (t0, t1) in enumerate(tl):
        for w in json.load(open(f'{W}/segtx/{k:02d}.json'))['words']:
            raw.append({'w': w['w'], 's': min(w['s'] + t0, t1), 'e': min(w['e'] + t0, t1)})
    ws = []
    for w in raw:
        t = w['w'].strip()
        if t.startswith('-') and ws:
            ws[-1]['w'] += t; ws[-1]['e'] = w['e']; continue
        ws.append({'w': t, 's': w['s'], 'e': w['e']})
    out, i = [], 0
    while i < len(ws):
        t = ws[i]['w']; low = t.lower().strip('.,?!')
        nxt = ws[i+1]['w'].lower().strip('.,?!') if i+1 < len(ws) else ''
        tail = t[len(t.rstrip('.,?!')):]
        if low == 'and' and nxt == 'well':
            ws[i+1]['w'] = 'animal' + ws[i+1]['w'][4:]; i += 1; continue
        if low == 'chat' and nxt == 'gbt':
            ws[i+1]['w'] = 'ChatGPT' + ws[i+1]['w'][3:]; i += 1; continue
        if low == 'plums': t = "Plumb's" + tail
        if low == "it's" and nxt == 'work' and out and out[-1]['w'].lower() == 'shows': t = 'its' + tail
        if low in ('attending', 'instinct'): t = low.capitalize() + tail
        mid = (ws[i]['s'] + ws[i]['e']) / 2
        beat = next((SEG[k][0] for k, (a, b) in enumerate(tl) if a <= mid < b), SEG[-1][0])
        out.append({'w': t, 's': ws[i]['s'], 'e': ws[i]['e'], 'beat': beat}); i += 1
    return out


def chunks(ws):
    out, cur = [], []
    for i, w in enumerate(ws):
        cur.append(w)
        nxt = ws[i + 1] if i + 1 < len(ws) else None
        end_punct = w['w'][-1] in '.,?!'
        if (len(cur) >= 4 or nxt is None or (end_punct and len(cur) >= 2) or
                (nxt and nxt['s'] - w['e'] > 0.35) or (nxt and nxt['beat'] != w['beat'])):
            out.append(cur); cur = []
    return out


def ts(t):
    h, m, s = int(t // 3600), int(t % 3600 // 60), t % 60
    return f'{h}:{m:02d}:{s:05.2f}'


def srt_ts(t):
    ms = int(round(t * 1000)); return f'{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}'


def clean(w):
    return w.rstrip('.,!').replace('{', '').replace('}', '')


def title_size(lines):
    f = ImageFont.truetype(FONT, 100)
    widest = max(f.getlength(l) for l in lines)
    return int(min(72, 100 * 940 / widest))


def build_ass(ws, total):
    tl, _ = timeline()
    head = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,Plus Jakarta Sans,64,&H00FFFFFF,&H00FFFFFF,&H70000000,&H90000000,-1,0,0,0,100,100,0,0,1,2,4,8,60,60,250,1
Style: Cap,Plus Jakarta Sans,68,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,3,2,60,60,470,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    for beat, lines in TITLES.items():
        spans = [tl[i] for i, sg in enumerate(SEG) if sg[0] == beat]
        st, en = spans[0][0], spans[-1][1]
        size = title_size(lines)
        ev.append(f'Dialogue: 1,{ts(st+0.05)},{ts(en-0.05)},Title,,0,0,0,,{{\\fs{size}\\fad(150,150)}}' + '\\N'.join(lines))
    srt = []
    for ci, ch in enumerate(chunks(ws)):
        c_end = ch[-1]['e'] + 0.15
        nxt = None
        for later in chunks(ws)[ci + 1:ci + 2]: nxt = later[0]['s']
        if nxt is not None: c_end = min(c_end + 0.25, nxt)
        for k, w in enumerate(ch):
            s = w['s'] if k else ch[0]['s']
            e = ch[k + 1]['s'] if k + 1 < len(ch) else c_end
            if e <= s: continue
            parts = [(f'{{\\c&H005076F1&}}{clean(x["w"])}{{\\c&H00FFFFFF&}}' if j == k else clean(x['w'])) for j, x in enumerate(ch)]
            ev.append(f'Dialogue: 0,{ts(s)},{ts(e)},Cap,,0,0,0,,' + ' '.join(parts))
        srt.append((ch[0]['s'], c_end, ' '.join(clean(x['w']) for x in ch)))
    open(f'{W}/reel.ass', 'w').write(head + '\n'.join(ev) + '\n')
    with open(f'{OUT}/captions.srt', 'w') as f:
        for i, (s, e, t) in enumerate(srt, 1):
            f.write(f'{i}\n{srt_ts(s)} --> {srt_ts(e)}\n{t}\n\n')


def overlay_images():
    im = Image.open(f'{UP}/476f366c-IMG_4514.HEIC').convert('RGB')
    im.crop((1656, 1142, 1656 + 3541, 1142 + 2370)).resize((2160, round(2160 * 2370 / 3541)), Image.LANCZOS).save(f'{W}/ov4.png')
    T = 'zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=rgb24'
    run(['ffmpeg', '-y', '-v', 'error', '-ss', '31', '-i', f'{ROOT}/source/IMG_4515.MOV', '-frames:v', '1',
         '-vf', f'{T},crop=1080:800:0:320,scale=2160:-2:flags=lanczos', f'{W}/ov5.png'])


def overlay_windows():
    tl, _ = timeline()
    def at(i, src_t=None):
        b, s, a, e = SEG[i]
        return tl[i][0] + ((src_t - a) if src_t else 0)
    w4 = (at(13), tl[16][1])          # "Attending, shows its work" .. "followed them all"
    w5 = (at(19, 94.75), tl[21][1])   # "puts the calculator" .. "check its work"
    return w4, w5


def final(total):
    (a4, b4), (a5, b5) = overlay_windows()
    def zoom(idx, d):
        n = int(d * 30) + 1
        return (f"[{idx}:v]scale=4320:-2,zoompan=z='1+0.07*on/{n}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x{{h}}:fps=30,"
                f"format=yuva420p,fade=t=in:st=0:d=0.25:alpha=1,fade=t=out:st={d-0.25:.2f}:d=0.25:alpha=1")
    h4 = round(1080 * Image.open(f'{W}/ov4.png').height / 2160 / 2) * 2
    h5 = round(1080 * Image.open(f'{W}/ov5.png').height / 2160 / 2) * 2
    y4, y5 = 1310 - h4, 1310 - h5
    fc = (zoom(1, b4 - a4).replace('{h}', str(h4)) + f",setpts=PTS-STARTPTS+{a4:.3f}/TB[o4];" +
          zoom(2, b5 - a5).replace('{h}', str(h5)) + f",setpts=PTS-STARTPTS+{a5:.3f}/TB[o5];" +
          f"[0:v][o4]overlay=0:{y4}:eof_action=pass:enable='between(t,{a4:.3f},{b4:.3f})'[v1];"
          f"[v1][o5]overlay=0:{y5}:eof_action=pass:enable='between(t,{a5:.3f},{b5:.3f})'[v2];"
          f"[v2]ass={W}/reel.ass:fontsdir=/root/.fonts[v]")
    # pass 1 loudness measure
    r = run(['ffmpeg', '-v', 'info', '-i', f'{W}/base.mp4', '-af', 'loudnorm=I=-14:TP=-1:LRA=11:print_format=json', '-f', 'null', '-'])
    js = json.loads(r.stderr[r.stderr.rfind('{'):r.stderr.rfind('}') + 1])
    ln = (f"loudnorm=I=-14:TP=-1:LRA=11:measured_I={js['input_i']}:measured_TP={js['input_tp']}:measured_LRA={js['input_lra']}:"
          f"measured_thresh={js['input_thresh']}:offset={js['target_offset']}:linear=true,alimiter=limit=0.79:attack=1:release=50:level=false,aresample=48000")
    run(['ffmpeg', '-y', '-v', 'error', '-i', f'{W}/base.mp4',
         '-loop', '1', '-t', f'{b4-a4:.3f}', '-i', f'{W}/ov4.png', '-loop', '1', '-t', f'{b5-a5:.3f}', '-i', f'{W}/ov5.png',
         '-filter_complex', fc, '-map', '[v]', '-map', '0:a', '-af', ln,
         '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-profile:v', 'high', '-pix_fmt', 'yuv420p', '-r', '30',
         '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-movflags', '+faststart', f'{OUT}/attending-reel-v1.mp4'])
    return (a4, b4), (a5, b5)


def edit_list(w4, w5):
    tl, total = timeline()
    ws = words_final()
    def mmss(t): return f'{int(t//60)}:{t%60:05.2f}'
    rows = ['# Attending reel v1: edit list', '', f'Total runtime: {mmss(total)}', '',
            '| Out | Beat | Clip | Source in | Source out | Words |', '|---|---|---|---|---|---|']
    for (b, s, a, e), (t0, t1) in zip(SEG, tl):
        txt = ' '.join(w['w'] for w in ws if t0 <= (w['s']+w['e'])/2 < t1)
        rows.append(f'| {mmss(t0)} | {b} | {SRC[s][2]} | {mmss(a)} | {mmss(e)} | {txt} |')
    rows += ['', '## Overlays', '',
             f'- {mmss(w4[0])} to {mmss(w4[1])}: IMG_4514.HEIC (Attending answer on Cerenia in a 14-week-old kitten, cropped to the answer panel, tabs and sidebar removed), slow zoom-in.',
             f'- {mmss(w5[0])} to {mmss(w5[1])}: IMG_4515.MOV still at 0:31 (Clinical Calculators list, browser tab strip cropped off), slow zoom-in.',
             '', 'Face audio continues underneath both overlays. Audio normalized to -14 LUFS integrated, -1 dBTP.']
    open(f'{OUT}/edit-list.md', 'w').write('\n'.join(rows) + '\n')


if __name__ == '__main__':
    step = sys.argv[1] if len(sys.argv) > 1 else 'all'
    _, total = timeline()
    if step in ('edl', 'all'):
        print('total', round(total, 2))
    if step in ('render', 'all'):
        stage_segments(); overlay_images()
        build_ass(words_final(), total)
        w4, w5 = final(total)
        edit_list(w4, w5)
        print('done')
