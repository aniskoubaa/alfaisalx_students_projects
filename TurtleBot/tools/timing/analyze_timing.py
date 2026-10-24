#!/usr/bin/env python3
"""Analyze a recording made by record_timing.py: find message gaps and what coincided with them.

Runs anywhere, standard library only (Python 3.10+). Reads the JSON Lines file, prints a text report and
optionally writes a CSV table of the gaps and a single self-contained HTML timeline.

    python analyze_timing.py timing.jsonl
    python analyze_timing.py timing.jsonl --min-gap 0.3 --window 1.0 --csv gaps.csv --html timeline.html

A gap is a time between two consecutive messages of one topic longer than max(3 x median interval, --min-gap).
All times are seconds since the recording started, on the robot's monotonic clock (its wall clock may be wrong).
Exit code 0 normally, 2 when the file cannot be read. See README.md for how to read the report.
"""
import argparse
import bisect
import csv
import gzip
import html
import json
import statistics
import sys

SKIP_GAP_TOPICS = ('/cmd_vel',)       # commands are sent when needed, not periodically
MOVING_EPS = 1e-3                     # m/s and rad/s above this count as "moving"
STAMP_STOPPED = 0.7                   # stamp gap / receive gap at or above this: the publisher stopped
STAMP_DELAYED = 0.4                   # at or below this: messages were produced on time but delivered late
MOTION_BEFORE = 3.0                   # s, default --motion-window: a motion start this long before the gap start counts
GROUP_WITHIN = 0.25                   # s, default --group-within: gaps of different topics starting this close are one event
BASE_TOPICS = ('/odom', '/tf', '/imu', '/wheel_status', '/wheel_vels', '/dock_status', '/battery_state')
MOTION_AFTER = 0.5                    # s, or this long after it (the last message before the gap is slightly earlier)
CPU_TOTAL_HIGH = 90.0                 # %
CPU_CORE_HIGH = 95.0                  # %
THROTTLE_NOW = 0x0F                   # low nibble of get_throttled: under-voltage, freq cap, throttled, temp limit now
ODOM_WARN, ODOM_ABORT = 0.3, 2.0      # the thresholds motion_shapes.py uses (hold still / abort)


# ---------------------------------------------------------------- loading
def load(path):
    """Return (header, records sorted by time, number of unreadable lines). A truncated last line is skipped."""
    header, recs, bad = {}, [], 0
    opener = gzip.open if str(path).endswith('.gz') else open      # .jsonl.gz is read transparently
    with opener(path, 'rt', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                bad += 1
                continue
            if not isinstance(d, dict):
                bad += 1
            elif d.get('kind') == 'header':
                header = d
            elif isinstance(d.get('t'), (int, float)):
                recs.append(d)
            else:
                bad += 1
    recs.sort(key=lambda r: r['t'])
    return header, recs, bad


# ---------------------------------------------------------------- gap detection
def find_gaps(times, min_gap=0.25):
    """times: sorted receive times of one topic. Returns (median interval, threshold, [(index, start, end)])."""
    if len(times) < 3:
        return None, None, []
    dts = [b - a for a, b in zip(times, times[1:])]
    med = statistics.median(dts)
    thr = max(3.0 * med, min_gap)
    return med, thr, [(i + 1, times[i], times[i + 1]) for i, d in enumerate(dts) if d > thr]


def classify_stamp(length, stamp_gap):
    """Compare the header-stamp gap with the receive gap of the same two messages."""
    if stamp_gap is None:
        return 'no stamp', 'topic has no header stamp'
    if length <= 0:
        return 'unclear', ''
    ratio = stamp_gap / length
    if ratio >= STAMP_STOPPED:
        return 'publisher stopped', 'stamp gap %.2f s ~ receive gap %.2f s: nothing was produced' % (stamp_gap, length)
    if ratio <= STAMP_DELAYED:
        return 'delivery delayed', 'stamp gap only %.2f s but receive gap %.2f s: produced on time, delivered late' % (stamp_gap, length)
    return 'unclear', 'stamp gap %.2f s vs receive gap %.2f s' % (stamp_gap, length)


def motion_starts(cmds):
    """Times at which /cmd_vel goes from zero (or unknown) to non-zero. cmds: records with vx, wz."""
    starts, moving = [], False
    for c in cmds:
        now = abs(c.get('vx', 0.0)) > MOVING_EPS or abs(c.get('wz', 0.0)) > MOVING_EPS
        if now and not moving:
            starts.append(c['t'])
        moving = now
    return starts


# ---------------------------------------------------------------- context of a gap
class Context:
    """Indexes the side data once so each gap can be looked up quickly. All times relative to t0."""

    def __init__(self, recs, t0, base_host):
        self.t0 = t0
        self.base_host = base_host
        self.sys = [r for r in recs if r['kind'] == 'sys']
        self.sys_t = [r['t'] - t0 for r in self.sys]
        self.pings = {}
        for r in recs:
            if r['kind'] == 'ping':
                self.pings.setdefault(r.get('host', '?'), []).append(r)
        self.events = []
        for r in recs:
            if r['kind'] == 'event':
                t = r['t']
                jt = r.get('jt')
                if jt is not None and abs(jt - t) < 5.0:      # journal timestamp is the better one when sane
                    t = jt
                self.events.append((t - t0, r.get('source', ''), r.get('text', '')))
        self.events.sort()
        self.thr = [(r['t'] - t0, r.get('value', 0)) for r in recs if r['kind'] == 'throttled']
        cmds = [r for r in recs if r['kind'] == 'msg' and r.get('topic') == '/cmd_vel']
        self.have_cmd = bool(cmds)
        starts = [(t - t0, '/cmd_vel zero to non-zero') for t in motion_starts(cmds)]
        docks = sorted((r for r in recs if r['kind'] == 'msg' and r.get('topic') == '/dock_status' and 'docked' in r),
                       key=lambda r: r['t'])
        self.have_dock = bool(docks)
        prev = None
        for r in docks:                                    # undock = is_docked true -> false
            if prev is True and r['docked'] is False:
                starts.append((r['t'] - t0, 'undock: /dock_status is_docked true to false'))
            prev = r['docked']
        self.starts = sorted(starts)
        self.cmd_t = [c['t'] - t0 for c in cmds]
        self.cmd_moving = [abs(c.get('vx', 0.0)) > MOVING_EPS or abs(c.get('wz', 0.0)) > MOVING_EPS for c in cmds]
        self.base_rtt = {}
        for h, lst in self.pings.items():
            ok = [p['rtt'] for p in lst if p.get('rtt') is not None]
            self.base_rtt[h] = statistics.median(ok) if ok else None

    def samples(self, lo, hi):
        return self.sys[bisect.bisect_left(self.sys_t, lo):bisect.bisect_right(self.sys_t, hi)]

    def around(self, a, b, pad, motion_window=MOTION_BEFORE):
        lo, hi = a - pad, b + pad
        ctx = {'window': (round(lo, 3), round(hi, 3))}
        sm = self.samples(lo, hi)
        ctx['n_samples'] = len(sm)
        if sm:
            alls = [s.get('cpu', {}).get('all') for s in sm if s.get('cpu', {}).get('all') is not None]
            ctx['cpu_max_total'] = max(alls) if alls else None
            cores = {}
            for s in sm:
                for k, v in s.get('cpu', {}).items():
                    if k != 'all':
                        cores[k] = max(cores.get(k, 0.0), v)
            ctx['cpu_max_core'] = max(cores.items(), key=lambda kv: kv[1]) if cores else None
            loads = [s['load'][0] for s in sm if s.get('load')]
            ctx['load1_max'] = max(loads) if loads else None
            procs = {}
            for s in sm:
                for k, v in s.get('procs', {}).items():
                    procs[k] = max(procs.get(k, 0.0), v)
            ctx['top_process'] = max(procs.items(), key=lambda kv: kv[1]) if procs else None
            temps = [s['temp'] for s in sm if 'temp' in s]
            ctx['temp_max'] = max(temps) if temps else None
            # network counters: from the last sample before the window (or the first inside) to the last inside
            i0 = bisect.bisect_left(self.sys_t, lo)
            first = self.sys[i0 - 1] if i0 > 0 else sm[0]
            last = sm[-1]
            errs, drops, links = {}, {}, {}
            for ifc, c1 in last.get('net', {}).items():
                c0 = first.get('net', {}).get(ifc)
                if c0:
                    e = (c1['rx_errs'] + c1['tx_errs']) - (c0['rx_errs'] + c0['tx_errs'])
                    d = (c1['rx_drop'] + c1['tx_drop']) - (c0['rx_drop'] + c0['tx_drop'])
                    if e:
                        errs[ifc] = e
                    if d:
                        drops[ifc] = d
            seen = {}
            for s in ([first] + sm):
                for ifc, st in s.get('link', {}).items():
                    seen.setdefault(ifc, set()).add(tuple(st))
            for ifc, states in seen.items():
                if len(states) > 1:
                    links[ifc] = sorted('/'.join(x) for x in states)
            ctx['net_errors'], ctx['net_drops'], ctx['link_changes'] = errs, drops, links
            wl = [s['wifi'] for s in sm if 'wifi' in s]
            ctx['wifi_level_min'] = min(x['level'] for x in wl) if wl else None
        pings = {}
        for h, lst in self.pings.items():
            inw = [p for p in lst if lo <= p['t'] - self.t0 <= hi]
            if inw:
                rtts = [p['rtt'] for p in inw if p.get('rtt') is not None]
                pings[h] = {'sent': len(inw), 'lost': len(inw) - len(rtts), 'max_rtt': max(rtts) if rtts else None,
                            'median_rtt': self.base_rtt.get(h)}
        ctx['pings'] = pings
        ctx['events'] = [(round(t, 3), src, txt) for t, src, txt in self.events if lo <= t <= hi]
        ctx['throttled'] = sorted({v & THROTTLE_NOW for t, v in self.thr if lo - 5.5 <= t <= hi and v & THROTTLE_NOW})
        near = [(s, lab) for s, lab in self.starts if a - motion_window <= s <= a + MOTION_AFTER]
        ctx['motion_start'] = near[-1][0] if near else None
        ctx['motion_label'] = near[-1][1] if near else None
        k = bisect.bisect_right(self.cmd_t, a) - 1
        ctx['moving_at_gap'] = self.cmd_moving[k] if k >= 0 else None
        return ctx


def verdicts_for(gap, ctx, others, base_host, cpu_thr=CPU_TOTAL_HIGH):
    """Human readable list of coincidences for one gap. others: names of other topics that also had a gap then."""
    v = []
    if ctx.get('motion_start') is not None:
        v.append('coincides with motion start (%s at %.2f s, %.2f s before the stall)' % (
            ctx.get('motion_label', 'motion'), ctx['motion_start'], gap['start'] - ctx['motion_start']))
    if ctx.get('moving_at_gap'):
        v.append('robot commanded to move (/cmd_vel non-zero) at gap start')
    cpu = ctx.get('cpu_max_total')
    if cpu is not None and cpu > cpu_thr:
        v.append('coincides with CPU > %g%% (total %.0f%%)' % (cpu_thr, cpu))
    core = ctx.get('cpu_max_core')
    if core and core[1] >= CPU_CORE_HIGH and not (cpu is not None and cpu > cpu_thr):
        v.append('one CPU core saturated (core %s at %.0f%%)' % core)
    p = ctx.get('pings', {}).get(base_host)
    if p and p['lost'] > 0:
        v.append('coincides with base ping loss (%d of %d lost to %s)' % (p['lost'], p['sent'], base_host))
    for h, p in ctx.get('pings', {}).items():
        if h != base_host and p['lost'] > 0:
            v.append('ping loss to %s (%d of %d)' % (h, p['lost'], p['sent']))
    if p and p['lost'] == 0 and p['max_rtt'] is not None and p['median_rtt'] and p['max_rtt'] > max(20.0, 10 * p['median_rtt']):
        v.append('base ping RTT spike (%.1f ms, median %.1f ms)' % (p['max_rtt'], p['median_rtt']))
    if ctx.get('events'):
        v.append('coincides with network/kernel event: ' + '; '.join('%s: %s' % (s, t[:70]) for _, s, t in ctx['events'][:2]))
    if ctx.get('net_errors') or ctx.get('net_drops'):
        v.append('network errors/drops during the gap: %s' % {**{k + ' errs': n for k, n in ctx.get('net_errors', {}).items()},
                                                             **{k + ' drops': n for k, n in ctx.get('net_drops', {}).items()}})
    if ctx.get('link_changes'):
        v.append('link state changed: %s' % ctx['link_changes'])
    if ctx.get('throttled'):
        v.append('Pi reported throttling/under-voltage (get_throttled bits %s)' % ', '.join(hex(x) for x in ctx['throttled']))
    if others:
        v.append('other topics stalled too: ' + ', '.join(others))
    if not v:
        v.append('no correlate found')
    return v


# ---------------------------------------------------------------- analysis
def analyze(header, recs, min_gap=0.25, window=0.5, base_host='192.168.186.2', cpu_thr=CPU_TOTAL_HIGH, topics=None,
            motion_window=MOTION_BEFORE, group_within=GROUP_WITHIN):
    t0 = header.get('mono0')
    if t0 is None:
        t0 = recs[0]['t'] if recs else 0.0
    t_end = max((r['t'] for r in recs), default=t0)
    ctx = Context(recs, t0, base_host)
    by_topic = {}
    for r in recs:
        if r['kind'] == 'msg':
            by_topic.setdefault(r['topic'], []).append(r)
    res = {'t0': t0, 'duration': max(t_end - t0, 0.0), 'topics': {}, 'gaps': [], 'base_host': base_host,
           'counts': {}, 'notes': [r.get('text', '') for r in recs if r['kind'] == 'note']}
    for r in recs:
        res['counts'][r['kind']] = res['counts'].get(r['kind'], 0) + 1
    for topic, lst in sorted(by_topic.items()):
        if topics and topic not in topics:
            continue
        times = [r['t'] - t0 for r in lst]
        stamps = [r.get('stamp') for r in lst]
        span = times[-1] - times[0] if len(times) > 1 else 0.0
        info = {'count': len(lst), 'rate': (len(lst) - 1) / span if span > 0 else None, 'median': None, 'max': None,
                'threshold': None, 'gaps': 0}
        if len(times) >= 2:
            dts = [b - a for a, b in zip(times, times[1:])]
            info['median'], info['max'] = statistics.median(dts), max(dts)
        if topic not in SKIP_GAP_TOPICS:
            med, thr, gaps = find_gaps(times, min_gap)
            info['threshold'] = thr
            info['gaps'] = len(gaps)
            for i, a, b in gaps:
                sg = None
                if stamps[i] is not None and stamps[i - 1] is not None:
                    sg = stamps[i] - stamps[i - 1]
                cls, why = classify_stamp(b - a, sg)
                res['gaps'].append({'topic': topic, 'start': a, 'end': b, 'length': b - a, 'stamp_gap': sg,
                                    'cls': cls, 'why': why, 'median': med})
        res['topics'][topic] = info
    res['gaps'].sort(key=lambda g: (g['start'], g['topic']))
    for g in res['gaps']:
        g['ctx'] = ctx.around(g['start'], g['end'], window, motion_window)
        others = sorted({o['topic'] for o in res['gaps'] if o is not g and o['topic'] != g['topic']
                         and o['start'] < g['end'] + window and o['end'] > g['start'] - window})
        g['others'] = others
        g['verdicts'] = verdicts_for(g, g['ctx'], others, base_host, cpu_thr)
    # group gaps of different topics that start within GROUP_WITHIN s of each other into one event
    events = []
    for g in res['gaps']:
        if events and g['start'] - events[-1]['last'] <= group_within:
            ev = events[-1]
            ev['gaps'].append(g)
            ev['end'] = max(ev['end'], g['end'])
            ev['last'] = g['start']
        else:
            events.append({'start': g['start'], 'end': g['end'], 'last': g['start'], 'gaps': [g]})
    for ev in events:
        ev['topics'] = sorted({g['topic'] for g in ev['gaps']})
        ev['length'] = max(g['length'] for g in ev['gaps'])
        main = next((g for g in ev['gaps'] if g['topic'] == '/odom'), ev['gaps'][0])
        ev['cls'], ev['why'] = main['cls'], main['why']
        ev['name'] = ('gap' if len(ev['topics']) == 1 else
                      'base stall' if all(t in BASE_TOPICS for t in ev['topics']) else 'multi-topic stall')
        ev['ctx'] = ctx.around(ev['start'], ev['end'], window, motion_window)
        others = sorted({o['topic'] for o in res['gaps'] if o['topic'] not in ev['topics']
                         and o['start'] < ev['end'] + window and o['end'] > ev['start'] - window})
        ev['verdicts'] = verdicts_for({'start': ev['start']}, ev['ctx'], others, base_host, cpu_thr)
        for g in ev['gaps']:
            g['event'] = events.index(ev) + 1
    res['events'] = events
    res['motion_window'] = motion_window
    res['group_within'] = group_within
    res['have_cmd'] = ctx.have_cmd
    res['have_dock'] = ctx.have_dock
    res['n_motion_starts'] = len(ctx.starts)
    res['ctx'] = ctx
    return res


# ---------------------------------------------------------------- output
def fmt(x, nd=2, unit=''):
    return '-' if x is None else ('%.*f%s' % (nd, x, unit))


def report(res, header, path, bad=0):
    L = []
    L.append('Timing report for %s' % path)
    L.append('Recording: %.1f s on the robot monotonic clock, host %s, %d records%s' % (
        res['duration'], header.get('hostname', '?'), sum(res['counts'].values()), ', %d unreadable lines skipped' % bad if bad else ''))
    if header.get('wall0') is not None:
        L.append('Robot wall clock at start: %.0f (epoch s; may be wrong, never used for correlation)' % header['wall0'])
    if 'footer' not in res['counts']:
        L.append('No footer record: the recording was cut off (killed or power loss); data up to then is used.')
    for n in res['notes']:
        L.append('Note from recorder: ' + n)
    if not res['have_cmd']:
        L.append('No /cmd_vel data: motion starts cannot be detected.')
    L.append('')
    L.append('%-16s %7s %9s %11s %9s %13s %5s' % ('topic', 'count', 'rate Hz', 'median ms', 'max ms', 'gap > (ms)', 'gaps'))
    for t, i in res['topics'].items():
        L.append('%-16s %7d %9s %11s %9s %13s %5s' % (
            t, i['count'], fmt(i['rate'], 1), fmt(None if i['median'] is None else i['median'] * 1000, 1),
            fmt(None if i['max'] is None else i['max'] * 1000, 0), fmt(None if i['threshold'] is None else i['threshold'] * 1000, 0),
            i['gaps'] if t not in SKIP_GAP_TOPICS else 'n/a'))
    L.append('')
    gaps = res['gaps']
    events = res['events']
    odom = [g for g in gaps if g['topic'] == '/odom']
    if '/odom' in res['topics']:
        L.append('/odom: %d gaps; %d longer than %.1f s (motion programs hold still), %d longer than %.1f s (they abort); longest %s s' % (
            len(odom), sum(g['length'] > ODOM_WARN for g in odom), ODOM_WARN, sum(g['length'] > ODOM_ABORT for g in odom), ODOM_ABORT,
            fmt(max((g['length'] for g in odom), default=None), 2)))
    L.append('%d gaps on all topics, grouped into %d events (gaps of different topics starting within %.2f s of each other are one event)' % (
        len(gaps), len(events), res['group_within']))
    L.append('')
    if not gaps:
        L.append('No gaps found.')
    for n, ev in enumerate(events, 1):
        c = ev['ctx']
        title = ev['name'] + (': ' + ' '.join(ev['topics']) if len(ev['topics']) > 1 else ': ' + ev['topics'][0])
        L.append('Event %d: %s  starts %.3f s  length %.3f s  [%s]' % (n, title, ev['start'], ev['length'], ev['cls']))
        if ev['why']:
            L.append('    stamps : ' + ev['why'])
        if c['n_samples']:
            core = c.get('cpu_max_core')
            tp = c.get('top_process')
            L.append('    cpu    : max total %s%%, busiest core %s; loadavg1 max %s; top process %s; temp max %s C' % (
                fmt(c.get('cpu_max_total'), 0), '%s at %.0f%%' % core if core else '-', fmt(c.get('load1_max'), 2),
                '%s %.0f%%' % tp if tp else '-', fmt(c.get('temp_max'), 1)))
            L.append('    network: errors %s, drops %s, link changes %s%s' % (
                c.get('net_errors') or 'none', c.get('net_drops') or 'none', c.get('link_changes') or 'none',
                ', wifi level min %s dBm' % c['wifi_level_min'] if c.get('wifi_level_min') is not None else ''))
        else:
            L.append('    cpu    : no system samples in the window')
        for h, p in c['pings'].items():
            L.append('    ping   : %s sent %d, lost %d, max RTT %s ms (median %s ms)' % (
                h, p['sent'], p['lost'], fmt(p['max_rtt'], 1), fmt(p['median_rtt'], 1)))
        for t, src, txt in c['events']:
            L.append('    event  : %.3f s [%s] %s' % (t, src, txt[:110]))
        if c['motion_start'] is not None:
            L.append('    motion : %s at %.2f s' % (c['motion_label'], c['motion_start']))
        elif res['have_cmd'] or res['have_dock']:
            L.append('    motion : no motion start within %.1f s before' % res['motion_window'])
        else:
            L.append('    motion : unknown (no /cmd_vel data)')
        for v in ev['verdicts']:
            L.append('    verdict: ' + v)
        for g in ev['gaps']:
            L.append('      %-14s start %.3f s  length %.3f s  [%s]%s' % (
                g['topic'], g['start'], g['length'], g['cls'], '  ' + g['why'] if g['why'] and len(ev['gaps']) > 1 else ''))
        L.append('')
    if events:
        tally = {}
        for ev in events:
            for v in ev['verdicts']:
                key = v.split(' (')[0].split(':')[0]
                tally[key] = tally.get(key, 0) + 1
        L.append('Summary of verdicts over %d events:' % len(events))
        for k, n in sorted(tally.items(), key=lambda kv: -kv[1]):
            L.append('  %3d  %s' % (n, k))
    return chr(10).join(L)


CSV_COLS = ['event', 'topic', 'start_s', 'end_s', 'length_s', 'stamp_gap_s', 'class', 'cpu_max_total', 'cpu_max_core', 'load1_max',
            'top_process', 'top_process_pct', 'ping_lost', 'ping_sent', 'ping_max_rtt_ms', 'net_errors', 'net_drops',
            'events', 'motion_start_s', 'verdicts']


def write_csv(res, path):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(CSV_COLS)
        for g in res['gaps']:
            c = g['ctx']
            p = c['pings'].get(res['base_host'], {})
            core, tp = c.get('cpu_max_core'), c.get('top_process')
            w.writerow([g.get('event', ''), g['topic'], '%.3f' % g['start'], '%.3f' % g['end'], '%.3f' % g['length'],
                        '' if g['stamp_gap'] is None else '%.3f' % g['stamp_gap'], g['cls'],
                        c.get('cpu_max_total', ''), '' if not core else '%s:%s' % core, c.get('load1_max', ''),
                        tp[0] if tp else '', tp[1] if tp else '', p.get('lost', ''), p.get('sent', ''),
                        p.get('max_rtt') if p.get('max_rtt') is not None else '',
                        sum(c.get('net_errors', {}).values()), sum(c.get('net_drops', {}).values()),
                        ' | '.join(t for _, _, t in c['events']), '' if c['motion_start'] is None else '%.3f' % c['motion_start'],
                        ' | '.join(g['verdicts'])])


def write_html(res, header, path, title='Timing timeline'):
    """One self-contained page: inline SVG, no scripts, no external files."""
    ctx, dur = res['ctx'], max(res['duration'], 1e-6)
    W, X0, ROW = 1100, 130, 22
    sx = (W - X0 - 20) / dur
    rows = [t for t in res['topics'] if t not in SKIP_GAP_TOPICS]
    y = 30
    parts = []
    step = max(1, round(dur / 10))
    for s in range(0, int(dur) + 1, step):
        x = X0 + s * sx
        parts.append('<line x1="%.1f" x2="%.1f" y1="20" y2="{H}" class="grid"/><text x="%.1f" y="14" class="lbl" text-anchor="middle">%d s</text>' % (x, x, x, s))
    for t in rows:
        parts.append('<text x="4" y="%d" class="lbl">%s</text><rect x="%d" y="%d" width="%.1f" height="6" class="ok"/>' % (
            y + 12, html.escape(t), X0, y + 5, dur * sx))
        for g in res['gaps']:
            if g['topic'] == t:
                parts.append('<rect x="%.1f" y="%d" width="%.1f" height="16" class="gap"><title>%s</title></rect>' % (
                    X0 + g['start'] * sx, y + 1, max(g['length'] * sx, 2), html.escape('%s gap %.2f s at %.2f s: %s' % (t, g['length'], g['start'], '; '.join(g['verdicts'])))))
        y += ROW + 4
    # motion (cmd_vel moving) band
    parts.append('<text x="4" y="%d" class="lbl">/cmd_vel moving</text>' % (y + 12))
    seg = None
    for tt, mv in zip(ctx.cmd_t + [dur], ctx.cmd_moving + [False]):
        if mv and seg is None:
            seg = tt
        if not mv and seg is not None:
            parts.append('<rect x="%.1f" y="%d" width="%.1f" height="12" class="mov"/>' % (X0 + seg * sx, y + 4, max((tt - seg) * sx, 1)))
            seg = None
    y += ROW + 4
    # CPU line
    parts.append('<text x="4" y="%d" class="lbl">CPU total %%</text><rect x="%d" y="%d" width="%.1f" height="50" class="box"/>' % (y + 30, X0, y, dur * sx))
    pts = ' '.join('%.1f,%.1f' % (X0 + t * sx, y + 50 - 0.5 * s['cpu']['all']) for t, s in zip(ctx.sys_t, ctx.sys) if s.get('cpu', {}).get('all') is not None)
    if pts:
        parts.append('<polyline points="%s" class="cpu"/>' % pts)
    y += 60
    # ping loss and events
    parts.append('<text x="4" y="%d" class="lbl">ping loss to %s</text>' % (y + 12, html.escape(res['base_host'])))
    for p in ctx.pings.get(res['base_host'], []):
        if p.get('rtt') is None:
            parts.append('<rect x="%.1f" y="%d" width="3" height="14" class="loss"/>' % (X0 + (p['t'] - ctx.t0) * sx, y + 2))
    y += ROW + 4
    parts.append('<text x="4" y="%d" class="lbl">network events</text>' % (y + 12))
    for t, src, txt in ctx.events:
        parts.append('<line x1="%.1f" x2="%.1f" y1="%d" y2="%d" class="ev"><title>%s</title></line>' % (
            X0 + t * sx, X0 + t * sx, y, y + 16, html.escape('%.2f s %s: %s' % (t, src, txt))))
    y += ROW + 8
    svg = '<svg viewBox="0 0 %d %d" width="100%%" role="img" aria-label="timeline">%s</svg>' % (W, y, ''.join(parts).replace('{H}', str(y)))
    rowshtml = ''.join('<tr><td>%s</td><td>%.2f</td><td>%.3f</td><td>%s</td><td>%s</td></tr>' % (
        html.escape(g['topic']), g['start'], g['length'], html.escape(g['cls']), html.escape('; '.join(g['verdicts']))) for g in res['gaps'])
    doc = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
           '<title>%s</title><style>body{font:14px system-ui,sans-serif;margin:16px;color:#222}'
           '.lbl{font:11px sans-serif;fill:#444}.grid{stroke:#ddd}.ok{fill:#cde3cd}.gap{fill:#d33}.mov{fill:#4a4}.box{fill:#f6f6f6;stroke:#ccc}'
           '.cpu{fill:none;stroke:#36c;stroke-width:1}.loss{fill:#d70}.ev{stroke:#808;stroke-width:2}'
           'table{border-collapse:collapse;margin-top:12px}td,th{border:1px solid #ccc;padding:3px 8px;text-align:left}'
           '</style></head><body><h1>%s</h1><p>%.1f s recorded on the robot monotonic clock, host %s. Red = gap, green = /cmd_vel non-zero, '
           'orange = lost ping, purple = network or kernel event. Hover a mark for details.</p>%s'
           '<table><tr><th>topic</th><th>start s</th><th>length s</th><th>stamps</th><th>verdict</th></tr>%s</table></body></html>') % (
        html.escape(title), html.escape(title), res['duration'], html.escape(str(header.get('hostname', '?'))), svg, rowshtml)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(doc)


def main(argv=None):
    ap = argparse.ArgumentParser(description='Analyze a record_timing.py recording.')
    ap.add_argument('file', help='JSON Lines file from record_timing.py (.jsonl or .jsonl.gz)')
    ap.add_argument('--min-gap', type=float, default=0.25, help='smallest gap in s to report (default 0.25)')
    ap.add_argument('--window', type=float, default=0.5, help='seconds of context on each side of a gap (default 0.5)')
    ap.add_argument('--base-host', default='192.168.186.2', help='address of the Create 3 base in the ping records')
    ap.add_argument('--cpu-threshold', type=float, default=CPU_TOTAL_HIGH, help='total CPU %% counted as high (default 90)')
    ap.add_argument('--topic', action='append', default=None, help='only analyze this topic (repeatable)')
    ap.add_argument('--motion-window', type=float, default=MOTION_BEFORE,
                    help='a motion start (cmd_vel zero to non-zero, or undock) up to this many s before a gap counts (default 3.0)')
    ap.add_argument('--group-within', type=float, default=GROUP_WITHIN,
                    help='gaps of different topics starting within this many s of each other form one event (default 0.25)')
    ap.add_argument('--csv', help='write the gaps as a CSV file')
    ap.add_argument('--html', help='write a self-contained HTML timeline')
    a = ap.parse_args(argv)
    try:
        header, recs, bad = load(a.file)
    except OSError as e:
        print('cannot read %s: %s' % (a.file, e), file=sys.stderr)
        return 2
    if not recs:
        print('no records in %s' % a.file, file=sys.stderr)
        return 2
    res = analyze(header, recs, a.min_gap, a.window, a.base_host, a.cpu_threshold, a.topic, a.motion_window, a.group_within)
    print(report(res, header, a.file, bad))
    if a.csv:
        write_csv(res, a.csv)
        print('\nCSV written to ' + a.csv)
    if a.html:
        write_html(res, header, a.html)
        print('HTML written to ' + a.html)
    return 0


if __name__ == '__main__':
    sys.exit(main())
