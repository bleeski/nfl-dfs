import csv, sys
src, out, a, b = sys.argv[1:5]
raw = list(csv.reader(open(src, newline='', encoding='utf-8-sig')))
ia = [i for i, r in enumerate(raw) if r and r[0].strip() == a][0]
ib = [i for i, r in enumerate(raw) if r and r[0].strip() == b][0]
raw[ia][4:10], raw[ib][4:10] = raw[ib][4:10], raw[ia][4:10]
with open(out, 'x', newline='', encoding='utf-8') as f:
    csv.writer(f, lineterminator='\r\n').writerows(raw)
