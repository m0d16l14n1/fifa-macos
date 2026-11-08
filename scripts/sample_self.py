#!/usr/bin/env python3
"""Self time per function for one thread of a macOS `sample` report.

usage: sample_self.py <sample.txt> <thread name substring> [--top N]
`sample` prints a call tree with inclusive counts; this subtracts each node's children to get the samples spent in
the function itself, and sums them by function name. Standard library only."""
import collections
import re
import sys

LINE = re.compile(r'^(?P<indent>[ +!:|]*)(?P<count>\d+) (?P<name>.+?)(?:  \(in [^)]*\))?(?:  \+ \d+)?(?:  \[.*)?$')


def main(argv):
    top = 30
    if '--top' in argv:
        i = argv.index('--top'); top = int(argv[i + 1]); del argv[i:i + 2]
    if len(argv) < 2:
        print(__doc__); return 2
    path, thread = argv
    lines = open(path, errors='replace').read().split('\n')
    start = next((i for i, l in enumerate(lines) if re.match(r'^ {4}\d+ Thread_', l) and thread in l), None)
    if start is None:
        print(f'no thread matching {thread!r}'); return 1
    total = int(lines[start].split()[0])
    nodes = []  # (depth, count, name)
    for l in lines[start + 1:]:
        if re.match(r'^ {4}\d+ Thread_', l) or not l.strip():
            break
        m = LINE.match(l)
        if not m:
            continue
        name = re.sub(r'\s+\S+\.(cpp|h|mm|c):\d+$', '', m.group('name')).strip()
        name = re.sub(r'\s+\+ \d+.*$', '', name)
        nodes.append((len(m.group('indent')), int(m.group('count')), name))
    self_time = collections.Counter()
    for i, (depth, count, name) in enumerate(nodes):
        children = 0
        # direct children: the following nodes at the first deeper depth, until one at this depth or shallower
        j, child_depth = i + 1, None
        while j < len(nodes) and nodes[j][0] > depth:
            if child_depth is None:
                child_depth = nodes[j][0]
            if nodes[j][0] == child_depth:
                children += nodes[j][1]
            j += 1
        self_time[name] += count - children
    print(f'{thread}: {total} samples')
    for name, n in self_time.most_common(top):
        print(f'  {n:6d} {100 * n / total:5.1f}%  {name[:130]}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
