#!/usr/bin/env python3
"""Write the AMCL settings for one route: config/localization_delivery.yaml plus the route's dock pose as AMCL's
initial pose.

Why: Nav2's lifecycle manager gives up after 60 s if the costmaps cannot find the map frame, and AMCL publishes the map
frame only after it has an initial pose. A program that sends the pose later is too late (seen in the simulator on
2026-11-05: "Failed to bring up all requested nodes"). With set_initial_pose AMCL starts already localized at the dock.

Usage (robot/start_stack.sh and sim/run_e2e.sh call it):
    python3 make_localization_params.py --route ROUTE_DIR/route.yaml --base config/localization_delivery.yaml --out FILE

The pose is the robot's pose on the dock, so the stack must be started with the robot on the dock.
"""
import argparse
import math
import sys

import yaml


def localization_params(base, dock_pose):
    """Return base (parsed yaml) with the dock pose (x, y, yaw in degrees) set as AMCL's initial pose."""
    amcl = base['amcl']['ros__parameters']
    amcl['set_initial_pose'] = True
    amcl['always_reset_initial_pose'] = False
    amcl['initial_pose'] = {'x': float(dock_pose['x']), 'y': float(dock_pose['y']), 'z': 0.0,
                            'yaw': math.radians(float(dock_pose['yaw']))}
    return base


def main(argv=None):
    ap = argparse.ArgumentParser(description='Write AMCL settings with the dock pose of a route as the initial pose.')
    ap.add_argument('--route', required=True, help='route.yaml')
    ap.add_argument('--base', required=True, help='config/localization_delivery.yaml')
    ap.add_argument('--out', required=True, help='file to write')
    args = ap.parse_args(argv)
    try:
        with open(args.route, encoding='utf-8') as fh:
            dock = yaml.safe_load(fh)['dock_pose']
        with open(args.base, encoding='utf-8') as fh:
            base = yaml.safe_load(fh)
        params = localization_params(base, dock)
    except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError) as e:
        print(f'ERROR: cannot make the localization settings: {e!r}', file=sys.stderr)
        return 2
    with open(args.out, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(f'# Written by make_localization_params.py from {args.base} and {args.route}. Do not edit.\n')
        yaml.safe_dump(params, fh, sort_keys=False)
    return 0


if __name__ == '__main__':
    sys.exit(main())
