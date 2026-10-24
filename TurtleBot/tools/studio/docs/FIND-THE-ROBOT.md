# Find the robot

The robot's address can change when it joins a different network. This page lists the ways to find it.

Guides: [First connection](FIRST-CONNECTION.md) | [Everyday use](EVERYDAY-USE.md) | [Find the robot](FIND-THE-ROBOT.md) | [Troubleshooting](TROUBLESHOOTING.md)

> Status: version 1.3 was tested offline and against the simulated robot only. Open real-robot checks: README [Not verified yet](../README.md#not-verified-yet).

## Which way to use

| Situation | Use |
|---|---|
| You can see the robot's screen | [Read the address on the screen](#1-read-the-address-on-the-robots-screen) |
| Normal day, same network | [Discover](#2-discover) |
| Discover finds nothing, but the robot is on the same Wi-Fi | [Search the whole network](#3-search-the-whole-network) |
| No known Wi-Fi in range | [The robot's own hotspot](#4-the-robots-own-hotspot) |
| Nothing else works, or first connection | [The cable](#5-the-ethernet-cable) |

## 1. Read the address on the robot's screen

The screen on top of the robot always shows its current address. This is always correct. Type it into the robot address box in Studio (or in the wizard, step 2) and press **Connect**.

The address `10.42.0.1` means the robot is running its own hotspot.

## 2. Discover

Press **Discover** on the Dashboard or in the wizard. Studio checks the places where the robot is usually found:

- the address it used last time on this network,
- `turtlebot4.local`,
- the robot's own hotspot address `10.42.0.1`,
- the cable address `192.168.185.3` and the cable's IPv6 link-local address.

Pick a reachable result and press **Connect**. Discover is quick and sends only a few requests. The name `turtlebot4.local` does not work on every network, for example some campus Wi-Fi.

## 3. Search the whole network

Use this when Discover finds nothing but the robot and your computer are on the same Wi-Fi.

1. Press **Search the whole network** (in the Discover results, or in wizard step 2).
2. Wait about 15 seconds. A progress bar shows how far it is.
3. Studio checks every address in the one local network your computer is on (a /24, at most 1024 addresses) for an open ssh port. It then asks the devices it found for their identity.
4. A result marked **Your robot (identity confirmed)** has the robot's known key. Press **Connect**.
5. Results marked "Other device with ssh" are not confirmed. Do not connect unless you know what the device is.

This is a small port-22 sweep of your own network. It runs only when you press the button. It cannot see other networks. Some networks stop devices from seeing each other (for example guest Wi-Fi). Then use the address on the robot's screen.

## 4. The robot's own hotspot

When no known Wi-Fi is in range, the robot starts its own network:

| | |
|---|---|
| Wi-Fi name | `Turtlebot4` (5 GHz) |
| Robot address | `10.42.0.1` |
| Internet | None |

1. Join `Turtlebot4` from your computer. Ask the lab maintainer for the password if you do not have it.
2. In Studio press **Discover**, or type `10.42.0.1`.

More about this mode: [HOW-TO-CONNECT.md, Step 2](../../../HOW-TO-CONNECT.md#step-2-find-out-which-network-the-robot-is-on-and-its-address).

To put the robot on a Wi-Fi network instead, use **Join a Wi-Fi network** in the Wi-Fi tab ([First connection, step 3](FIRST-CONNECTION.md#3-put-the-robot-on-the-network-you-will-use)).

## 5. The Ethernet cable

Plug a cable between your computer and the robot. The robot is at `192.168.185.3`, but your computer normally gets no matching address on the cable, so Studio finds it by its IPv6 link-local address (`fe80::...`). No network setting needs to change. This works with no Wi-Fi at all. Details: [Connect with an Ethernet cable](../../../HOW-TO-CONNECT.md#connect-with-an-ethernet-cable-no-wi-fi-needed).

## After you find it

Studio remembers the address for each network, so Discover usually finds the robot again next time. If the robot's address changes, start again from way 1.

If none of this works: [Troubleshooting](TROUBLESHOOTING.md).
