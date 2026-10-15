import sys, hashlib
sys.path.insert(0, '/tmp/claude-0/-home-user-nfl-dfs/2bcf0cfe-60b8-5dd0-86f4-7e62c57ce802/scratchpad/review')
from lib import *
# usage: apply.py src dst "eid:out:in" ... | "move:eidA:eidB"
src, dst = sys.argv[1], sys.argv[2]
lines, rows = load(src)
byeid = {r['eid']: r for r in rows}
for op in sys.argv[3:]:
    p = op.split(':')
    if p[0] == 'move':
        a, b = byeid[p[1]], byeid[p[2]]
        a['ids'], b['ids'] = b['ids'], a['ids']
    else:
        r = byeid[p[0]]; k = r['ids'].index(p[1]); r['ids'][k] = p[2]
for r in rows:
    c = lines[r['i']].decode('utf-8').split(',')
    c[4:10] = r['ids']
    lines[r['i']] = ','.join(c).encode('utf-8')
out = b'\r\n'.join(lines)
open(dst, 'wb').write(out)
print(hashlib.sha256(out).hexdigest())
# byte diff: only cells 4-9 changed
o = open(src, 'rb').read().split(b'\r\n'); n = out.split(b'\r\n')
assert len(o) == len(n)
for a, b in zip(o, n):
    if a != b:
        ca, cb = a.decode().split(','), b.decode().split(',')
        assert len(ca) == len(cb) and all(ca[i] == cb[i] for i in range(len(ca)) if i not in range(4, 10)), 'non-roster cell changed'
print('byte check ok')
