#!/usr/bin/env python3
"""Summarizes an Instruments Metal System Trace: GPU time by channel and by encoder label.

usage: gpu_intervals.py <file.trace> [--top N]
Exports the metal-gpu-intervals table with xctrace and prints, for the recorded span: GPU busy time per channel
(Vertex, Fragment, Compute, Blit), and the encoders (labels; turn on metal_debug_labels for pass labels) ranked
by total time. Standard library only."""
import collections
import subprocess
import sys
import xml.etree.ElementTree as ET


def rows(trace):
    xml = subprocess.run(['xctrace', 'export', '--input', trace, '--xpath',
                          '/trace-toc/run[@number="1"]/data/table[@schema="metal-gpu-intervals"]'],
                         capture_output=True, check=True).stdout
    root = ET.fromstring(xml)
    node = root.find('node')
    cols = [c.findtext('mnemonic') for c in node.find('schema').findall('col')]
    cache = {}
    for row in node.findall('row'):
        values = {}
        for el in row.iter():
            if 'id' in el.attrib:
                cache[el.attrib['id']] = el
        for name, el in zip(cols, list(row)):
            if 'ref' in el.attrib:
                el = cache[el.attrib['ref']]
            values[name] = el
        yield values


def main(argv):
    top = 25
    if '--top' in argv:
        i = argv.index('--top'); top = int(argv[i + 1]); del argv[i:i + 2]
    if not argv:
        print(__doc__); return 2
    by_channel = collections.Counter()
    by_label = collections.Counter()
    count_label = collections.Counter()
    first = last = None
    for r in rows(argv[0]):
        start = int(r['start'].text or 0)
        dur = int(r['duration'].text or 0)
        first = start if first is None else min(first, start)
        last = start + dur if last is None else max(last, start + dur)
        channel = r['channel-name'].get('fmt', '')
        by_channel[channel] += dur
        label = r['channel-subtitle'].get('fmt', '') if r.get('channel-subtitle') is not None else ''
        label = label or r['event-label'].get('fmt', '')
        # "<command buffer label>:<encoder label>  (<process>) <encoder id>": the id and process apart.
        label = label.split('  (')[0]
        by_label[(channel, label)] += dur
        count_label[(channel, label)] += 1
    span = (last - first) / 1e6
    print(f'span {span:.0f} ms')
    for channel, ns in by_channel.most_common():
        print(f'  {channel:12s} {ns / 1e6:9.1f} ms  ({100 * ns / 1e6 / span:.0f}% of the span)')
    print(f'top {top} encoders by total time:')
    for (channel, label), ns in by_label.most_common(top):
        print(f'  {ns / 1e6:8.2f} ms  {count_label[(channel, label)]:5d}x  {channel:9s} {label[:110]}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
