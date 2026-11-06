#!/usr/bin/env python3
"""Write a synthetic hall for the delivery simulator: a Nav2 map (route_map.yaml + route_map.pgm), a matching route
spec for tools/plan_route.py (route_spec.yaml) and the ground truth the simulator and the analysis need
(sim_world.json). Standard library only; it only writes files and never touches a robot.

    python3 sim_map.py --out DIR [--goal-x 60] [--pickup-timeout 600] [--leg-timeout 600]

The hall (map frame, metres, 5 cm cells, image 70 m x 12 m, origin (-2, -5)):
  - hall interior x 0..66, y 0..6.5; the straight wall the robot follows is the south wall at y = 0
  - the dock is at (1.5, 0.5) facing +x, the pickup spot at (goal-x, 0.5)
  - a glass room x 28..34, y -4..0 opens off the south wall. The lidar sees through its glass front, so the MAP
    shows it as a big free pocket; the real glass (ground truth, not in the map) closes it except a 1.5 m doorway
  - two glass-door recesses x 44..45.4 and 50..51.4: the map shows a 2 m deep pocket (the lidar sees through the
    doors), the glass itself is 0.4 m behind the wall line (ground truth only)
  - keepout lines across the room opening and the two doors, one slow zone (50 %) at x 38..40

sim_world.json holds: glass_segments (ground truth only), glass_room (rectangle the robot must never enter),
straight_ranges (x ranges where the wall is a plain straight wall), wall_y, wall_offset_m, clearance values.
"""
import argparse
import json
import math
import os
import sys

# ---------------------------------------------------------------- constants (metres)
RES = 0.05                      # m per cell
WIDTH_M, HEIGHT_M = 70.0, 12.0  # image size
ORIGIN = (-2.0, -5.0)           # map position of the bottom-left corner
HALL_X1, HALL_Y1 = 66.0, 6.5    # hall interior is x 0..HALL_X1, y 0..HALL_Y1
WALL_T = 0.10                   # wall thickness
ROOM = (28.0, -4.0, 34.0, 0.0)  # glass room x0, y0, x1, y1
ROOM_DOORWAY = (30.0, 31.5)     # x range of the doorway in the room's glass front
DOORS = [(44.0, 45.4), (50.0, 51.4)]   # glass door recesses (x ranges)
DOOR_GLASS_Y = -0.4             # glass plane of a door recess
DOOR_POCKET_DEPTH = 2.0         # depth of the pocket the lidar sees behind the doors
DOCK = (1.5, 0.5, 0.0)          # dock pose x, y, yaw degrees
START_AHEAD = 0.7
LANE_Y = 0.5
STRAIGHT_RANGES = [(4.0, 26.0), (36.0, 43.0), (53.0, 59.0)]   # plain wall, away from room and doors
WALL_OFFSET = 0.5
CLEARANCE = 0.30
UNKNOWN, FREE, OCC = 205, 254, 0


def idx(v, o):
    """Position in cells from the origin; rounded first because 30.0 // 0.05 is 599.0 in floating point."""
    return round((v - o) / RES, 6)


def build_grid():
    W, H = int(round(WIDTH_M / RES)), int(round(HEIGHT_M / RES))
    rows = [bytearray([UNKNOWN]) * W for _ in range(H)]

    def fill(x0, y0, x1, y1, value):
        """Set the cells inside the rectangle (x0, y0)-(x1, y1) metres; row 0 of the image is the top."""
        c0, c1 = max(int(math.floor(idx(x0, ORIGIN[0]))), 0), min(int(math.ceil(idx(x1, ORIGIN[0]))), W)
        j0, j1 = int(math.floor(idx(y0, ORIGIN[1]))), int(math.ceil(idx(y1, ORIGIN[1])))
        for r in range(max(H - j1, 0), min(H - j0, H)):
            rows[r][c0:c1] = bytes([value]) * max(c1 - c0, 0)

    t = WALL_T
    # outer walls, then the hall interior
    fill(-t, -t, HALL_X1 + t, HALL_Y1 + t, OCC)
    fill(0.0, 0.0, HALL_X1, HALL_Y1, FREE)
    # glass room: cut the south wall, free pocket, solid back and side walls (the lidar sees these through the glass)
    x0, y0, x1, y1 = ROOM
    fill(x0 - t, y0 - t, x1 + t, y1, OCC)
    fill(x0, y0, x1, 0.05, FREE)
    # door pockets (the lidar sees through the glass to a corridor behind)
    for a, b in DOORS:
        fill(a - t, -DOOR_POCKET_DEPTH - t, b + t, 0.0, OCC)
        fill(a, -DOOR_POCKET_DEPTH, b, 0.05, FREE)
    return W, H, rows


def write_pgm(path, W, H, rows):
    with open(path, 'wb') as fh:
        fh.write(f'P5\n# synthetic delivery hall\n{W} {H}\n255\n'.encode())
        fh.write(b''.join(bytes(r) for r in rows))


def glass_segments():
    """Ground-truth glass (not in the map): [x1, y1, x2, y2] per segment."""
    x0, y0, x1, y1 = ROOM
    segs = [[x0, 0.0, ROOM_DOORWAY[0], 0.0], [ROOM_DOORWAY[1], 0.0, x1, 0.0]]
    for a, b in DOORS:
        segs.append([a, DOOR_GLASS_Y, b, DOOR_GLASS_Y])
    return segs


def spec_text(goal_x, pickup_timeout, leg_timeout):
    x0, y0, x1, y1 = ROOM
    lines = [
        '# Route spec for the synthetic hall written by sim_map.py (tools/plan_route.py input).',
        f'dock_pose: {{x: {DOCK[0]}, y: {DOCK[1]}, yaw: {DOCK[2]}}}',
        f'start: {{x: {DOCK[0] + START_AHEAD}, y: {DOCK[1]}}}',
        f'goal: {{x: {goal_x}, y: {LANE_Y}, yaw: 0.0}}',
        f'wall_offset_m: {WALL_OFFSET}',
        f'clearance_m: {CLEARANCE}',
        'lane_half_width_m: 0.25',
        'waypoint_spacing_m: 3.0',
        'keepout_lines:',
        '  - name: glass_room_opening',
        f'    from: [{x0}, 0.0]',
        f'    to: [{x1}, 0.0]',
        '    width_m: 0.10',
    ]
    for i, (a, b) in enumerate(DOORS, 1):
        lines += [f'  - name: glass_door_{i}', f'    from: [{a}, 0.0]', f'    to: [{b}, 0.0]', '    width_m: 0.10']
    lines += [
        'slow_zones:',
        '  - name: cable',
        '    speed_percent: 50',
        '    points: [[38.0, 0.0], [40.0, 0.0], [40.0, 1.5], [38.0, 1.5]]',
        'settings:',
        f'  pickup_timeout_s: {pickup_timeout}',
        f'  leg_timeout_s: {leg_timeout}',
        '  handoff_timeout_s: 120',
        '  hands_clear_s: 3',
        '  button_placed: 3',
        '  button_received: 4',
    ]
    return '\n'.join(lines) + '\n'


def world_dict(goal_x):
    x0, y0, x1, y1 = ROOM
    return {
        'resolution': RES, 'origin': list(ORIGIN),
        'dock_pose': {'x': DOCK[0], 'y': DOCK[1], 'yaw': DOCK[2]},
        'goal': {'x': goal_x, 'y': LANE_Y},
        'wall_y': 0.0, 'wall_offset_m': WALL_OFFSET, 'clearance_m': 0.20, 'planner_clearance_m': CLEARANCE,
        'straight_ranges': [list(r) for r in STRAIGHT_RANGES if r[0] < goal_x],
        'glass_room': [x0, y0, x1, y1],
        'glass_segments': glass_segments(),
        'robot_radius_m': 0.17,
    }


def write_all(out, goal_x=60.0, pickup_timeout=600, leg_timeout=600):
    os.makedirs(out, exist_ok=True)
    W, H, rows = build_grid()
    write_pgm(os.path.join(out, 'route_map.pgm'), W, H, rows)
    with open(os.path.join(out, 'route_map.yaml'), 'w', newline='\n') as fh:
        fh.write(f'image: route_map.pgm\nmode: trinary\nresolution: {RES}\norigin: [{ORIGIN[0]}, {ORIGIN[1]}, 0.0]\n'
                 'negate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\n')
    with open(os.path.join(out, 'route_spec.yaml'), 'w', newline='\n') as fh:
        fh.write(spec_text(goal_x, pickup_timeout, leg_timeout))
    with open(os.path.join(out, 'sim_world.json'), 'w', newline='\n') as fh:
        json.dump(world_dict(goal_x), fh, indent=1)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description='Write the synthetic hall for the delivery simulator.')
    ap.add_argument('--out', required=True, help='output folder (created)')
    ap.add_argument('--goal-x', type=float, default=60.0, help='x of the pickup spot, m (default 60; use 20 for a short run)')
    ap.add_argument('--pickup-timeout', type=int, default=600, help='route setting pickup_timeout_s')
    ap.add_argument('--leg-timeout', type=int, default=600, help='route setting leg_timeout_s')
    a = ap.parse_args(argv)
    if not 8.0 <= a.goal_x <= 62.0:
        print('--goal-x must be between 8 and 62', file=sys.stderr)
        return 2
    write_all(a.out, a.goal_x, a.pickup_timeout, a.leg_timeout)
    print(f'wrote route_map.yaml/.pgm, route_spec.yaml, sim_world.json in {a.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
