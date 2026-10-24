## TEST AGENT PROMPT – IMAGE INTEGRATION RULES ##
- Always use base64-encoded images; JPEG, PNG, WEBP only.
- Do not upload blank, solid-color, or uniform images; images must contain real visual features.
- Transcode non-PNG/JPEG to PNG/JPEG; re-detect MIME after transforms.
- Animated images: first frame only. Resize large images.
For CricAnalyze video tests: a sample MP4 can be built from /app/frontend/public/images/hero.jpg with cv2 (5s, 25fps, 480x720, mp4v).
