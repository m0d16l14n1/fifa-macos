#!/usr/bin/env python3
"""Summarizes a present log (--present_log=<file.csv>): how evenly game frames reach the screen.

usage: present_stats.py <file.csv> [--from SECONDS] [--to SECONDS]
For the presents in the window (seconds from the first line): frames presented, presents that showed the same
game frame as the one before (a repeat: the picture held for another refresh), game frames never presented
(replaced in the mailbox before a present), the present interval percentiles, and the motion step: the time
between the moments two consecutive shown frames were made (the game time the picture advances by). The present
interval can be a steady 16.7 ms while the motion step varies (frames made unevenly, sampled at each refresh):
that is judder. Standard library only."""
import sys


def main(argv):
    lo = hi = None
    if '--from' in argv:
        i = argv.index('--from'); lo = float(argv[i + 1]); del argv[i:i + 2]
    if '--to' in argv:
        i = argv.index('--to'); hi = float(argv[i + 1]); del argv[i:i + 2]
    if not argv:
        print(__doc__); return 2
    t0 = None
    presents, refreshes = [], []
    made = {}  # refresh number -> when the game frame was published
    for line in open(argv[0]):
        f = line.strip().split(',')
        if f[0] not in ('r', 'p'):
            continue
        t = int(f[1]) / 1e9
        t0 = t if t0 is None else t0
        s = t - t0
        if (lo is not None and s < lo) or (hi is not None and s > hi):
            continue
        if f[0] == 'r':
            refreshes.append(int(f[2]))
            made[int(f[2])] = t
        elif f[4] in ('0', '1'):  # presented (or presented the UI only)
            presents.append((t, int(f[2]), f[3]))
    if len(presents) < 3:
        print('too few presents'); return 1
    repeats = sum(1 for a, b in zip(presents, presents[1:]) if b[1] == a[1])
    shown = {p[1] for p in presents}
    skipped = sum(1 for r in set(refreshes) if r and r not in shown and min(shown) < r < max(shown))
    gaps = sorted((b[0] - a[0]) * 1000 for a, b in zip(presents, presents[1:]))
    pct = lambda q: gaps[min(len(gaps) - 1, int(q * len(gaps)))]
    span = presents[-1][0] - presents[0][0]
    steps = []
    last = None
    for p in presents:
        if p[1] in made and p[1] != (last[1] if last else None):
            if last and last[1] in made:
                steps.append((made[p[1]] - made[last[1]]) * 1000)
            last = p
    steps.sort()
    spct = lambda q: steps[min(len(steps) - 1, int(q * len(steps)))] if steps else 0
    mean = sum(steps) / len(steps) if steps else 0
    dev = (sum((x - mean) ** 2 for x in steps) / len(steps)) ** 0.5 if steps else 0
    threads = {}
    for p in presents: threads[p[2]] = threads.get(p[2], 0) + 1
    print(f'{len(presents)} presents in {span:.1f} s ({len(presents) / span:.1f}/s), {len(shown)} game frames shown '
          f'({len(shown) / span:.1f}/s); repeats {repeats} ({100 * repeats / len(presents):.1f}%), game frames never '
          f'shown {skipped}; present interval p50 {pct(.5):.2f} p95 {pct(.95):.2f} p99 {pct(.99):.2f} ms; '
          f'by thread {threads}')
    print(f'  motion step p5 {spct(.05):.2f} p50 {spct(.5):.2f} p95 {spct(.95):.2f} ms, deviation {dev:.2f} ms')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
