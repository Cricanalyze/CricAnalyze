# Build a truly occluded clip (legs of batter hidden) and run batting pipeline
import sys, json, cv2
sys.path.insert(0, '/app/backend')
import pose_pipeline as pp
src = cv2.VideoCapture('/root/testvids/bat.mp4')
fps = src.get(5)
vw = cv2.VideoWriter('/tmp/occluded_legs.mp4', cv2.VideoWriter_fourcc(*'mp4v'), fps, (1920, 1080))
first = None
while True:
    ok, f = src.read()
    if not ok:
        break
    cv2.rectangle(f, (0, 760), (1100, 1080), (40, 40, 40), -1)
    if first is None:
        first = f.copy()
    vw.write(f)
vw.release()
cv2.imwrite('/tmp/f_occl_legs.jpg', cv2.resize(first, (640, 360)))
r, imgs = pp.analyse_video('/tmp/occluded_legs.mp4', 'batting', 'side_on', {'width': 1920, 'height': 1080, 'fps': fps})
print(json.dumps({'status': r['status'], 'quality': r['quality'], 'phases': [(p['key'], p['status']) for p in r['phases']],
                  'metrics': [(m['key'], m['value'], m['status'], m.get('confidence'), m.get('reason')) for m in r['metrics']], 'score': r['score']}, default=str, indent=1))
