"""Central voiceover script lines, shared by:
  - studio.py   (cloud build — composites the audio into the videos)
  - make_vo.py  (your Mac — generates ElevenLabs audio in YOUR voice)

Keys are stable filenames. make_vo.py writes vo_eleven/<key>.mp3; studio.py
prefers those over the free Piper voice when present. Keep the text EXACTLY in
sync with the lines used in studio.py.
"""

VO = {
    "hook": "Your next customer is already scrolling.",
    "brand": "Springs Creative Marketing. Strategy, not guesswork.",
    "main_websites": "Websites that feel modern, load fast, and convert.",
    "main_seo": "We sharpen your local search with clean SEO.",
    "main_social": "Social that sounds like you, and brings in real leads.",
    "main_ai": "Plus practical AI to spot opportunities and save time.",
    "cta": "Book your free marketing audit today.",
    "svc_websites": "Your website is your first impression. We build sites that are modern, fast, and built to convert.",
    "svc_local-seo": "When your neighbors search, be the first name they find, with clean local SEO and smart content.",
    "svc_social": "Your brand has a voice. We run social campaigns that sound like you, and bring in real leads.",
    "svc_ai-edge": "Want an edge? We use practical AI to spot opportunities and save you time.",
}
