"""Helper: parse a locale .ts file with flat keys into a dict."""
import re

LINE_RE = re.compile(r'^\s{4}"([^"]+)":\s*"((?:\\.|[^"\\])*)"(,?)\s*$', re.MULTILINE)


def parse_ts(path):
    with open(path, 'r', encoding='utf-8') as f:
        src = f.read()
    out = {}
    order = []
    for m in LINE_RE.finditer(src):
        k = m.group(1)
        v = m.group(2)
        out[k] = v
        order.append(k)
    return out, order, src


if __name__ == '__main__':
    import sys, io, json
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    d, order, src = parse_ts(sys.argv[1])
    print('keys:', len(d))
    if len(sys.argv) > 2:
        # print v3.12 overlap
        with open(sys.argv[2], 'r', encoding='utf-8') as f:
            v312 = json.load(f)
        present = [k for k in v312 if k in d]
        missing = [k for k in v312 if k not in d]
        print('v312 present:', len(present), 'missing:', len(missing))
        if missing[:5]:
            print('first missing:', missing[:5])
