import sys, json, os, subprocess, numpy as np
from faster_whisper import WhisperModel
m = WhisperModel('medium.en', device='cpu', compute_type='int8', cpu_threads=4)
for path in sys.argv[2:]:
    out = os.path.join(sys.argv[1], os.path.basename(path).rsplit('.',1)[0] + '.json')
    if os.path.exists(out): print('cached', out); continue
    raw = subprocess.run(['ffmpeg','-v','error','-i',path,'-ac','1','-ar','16000','-f','s16le','-'],capture_output=True,check=True).stdout
    audio = np.frombuffer(raw,np.int16).astype(np.float32)/32768
    segs, info = m.transcribe(audio, word_timestamps=True, vad_filter=False, condition_on_previous_text=False,
        initial_prompt="Plumb's, AAVSB, Attending by Instinct, veterinarians, Dr. Katie Jackson.")
    words = []
    for s in segs:
        for w in s.words: words.append({'w': w.word, 's': round(w.start,3), 'e': round(w.end,3), 'p': round(w.probability,3)})
    json.dump({'file': path, 'duration': info.duration, 'words': words}, open(out,'w'), indent=0)
    print('done', out, len(words))
