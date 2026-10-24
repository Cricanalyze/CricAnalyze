# Pose pipeline acceptance: per-clip batting + bowling template check (run manually; slow on CPU)
import sys, json, cv2
sys.path.insert(0, '/app/backend')
import pose_pipeline as pp

VIDS = '/root/testvids'
out = {}
for name, kind in [('bat', 'batting'), ('distant', 'batting'), ('occluded', 'batting'), ('lowres', 'batting'), ('bat', 'bowling')]:
    c = cv2.VideoCapture(f'{VIDS}/{name}.mp4')
    meta = {'width': int(c.get(3)), 'height': int(c.get(4)), 'fps': c.get(5)}
    c.release()
    try:
        r, imgs = pp.analyse_video(f'{VIDS}/{name}.mp4', kind, 'side_on', meta)
        res = {'meta': meta, 'status': r['status'], 'usable': r['quality']['usable'], 'quality': r['quality'],
               'phases': [(p['key'], p['status']) for p in r['phases']],
               'metrics': [(m['key'], m['name'], m['value'], m['status'], m.get('reason')) for m in r['metrics']],
               'score': r['score'], 'n_imgs': len(imgs)}
        # invariants
        bad = []
        for m in r['metrics']:
            if m['status'] == 'not_measurable' and m['value'] is not None:
                bad.append(f"{m['key']} not_measurable but value set")
        sc = r['score']
        if sc.get('value') is not None:
            inc = len(sc.get('included', []))
            if inc < 3 or sc.get('coverage', 0) < 0.6 or sc.get('detected_phases', 0) < 2:
                bad.append('score given despite thresholds unmet')
        elif sc.get('reason') != 'Insufficient evidence to calculate a reliable score.':
            bad.append('missing insufficient reason')
        names = {k for k, _ in pp.PHASES[kind]}
        if {k for k, _ in res['phases']} != names:
            bad.append('phase keys mismatch template')
        res['violations'] = bad
    except Exception as e:
        import traceback
        res = {'error': repr(e), 'tb': traceback.format_exc()}
    out[f'{name}:{kind}'] = res
    print(name, kind, json.dumps(res, default=str), flush=True)
json.dump(out, open('/tmp/pose_acceptance.json', 'w'), default=str, indent=1)
print('DONE', flush=True)
