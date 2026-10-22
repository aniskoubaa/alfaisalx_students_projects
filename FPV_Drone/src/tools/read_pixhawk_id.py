"""Read a Pixhawk's identity over USB. Read-only: never arms, never sets parameters.

Usage: python read_pixhawk_id.py [COMx]   (needs: pip install pymavlink pyserial)
Prints the USB descriptor (incl. the USB serial string), the MAVLink
AUTOPILOT_VERSION (firmware, board, 64-bit UID and 18-byte UID2), the banner /
STATUSTEXT lines, and on PX4 the output of `ver all` from the MAVLink shell.
"""
import sys
import time

from pymavlink import mavutil
from serial.tools import list_ports

HOLYBRO_VID = 0x3162
HINTS = ("px4", "pixhawk", "ardupilot", "fmu", "holybro", "cube", "chibios")


def pick_port(arg):
    ports = list(list_ports.comports())
    print("=== Serial ports ===")
    for p in ports:
        vidpid = f"{p.vid:04X}:{p.pid:04X}" if p.vid is not None else "-"
        print(f"{p.device}: {p.description} | VID:PID {vidpid} | USB serial {p.serial_number} "
              f"| manufacturer {p.manufacturer} | product {p.product} | {p.hwid}")
    if arg:
        return arg, ports
    for p in ports:
        text = f"{p.description} {p.manufacturer} {p.product}".lower()
        if p.vid == HOLYBRO_VID or any(h in text for h in HINTS):
            return p.device, ports
    if len(ports) == 1:
        return ports[0].device, ports
    sys.exit("No Pixhawk-looking port found; pass the COM port as an argument.")


def fw_version(v):
    types = {0: "dev", 64: "alpha", 128: "beta", 192: "rc", 255: "official"}
    return f"{(v >> 24) & 0xFF}.{(v >> 16) & 0xFF}.{(v >> 8) & 0xFF} ({types.get(v & 0xFF, v & 0xFF)})"


def px4_shell(m, cmd, seconds=4.0):
    """Run one command in the PX4 MAVLink shell (SERIAL_CONTROL, device 10)."""
    flags = (mavutil.mavlink.SERIAL_CONTROL_FLAG_RESPOND
             | mavutil.mavlink.SERIAL_CONTROL_FLAG_EXCLUSIVE
             | mavutil.mavlink.SERIAL_CONTROL_FLAG_MULTI)
    data = list((cmd + "\n").encode())
    m.mav.serial_control_send(10, flags, 0, 0, len(data), data + [0] * (70 - len(data)))
    out, end = bytearray(), time.time() + seconds
    while time.time() < end:
        msg = m.recv_match(type="SERIAL_CONTROL", blocking=True, timeout=0.5)
        if msg and msg.count:
            out += bytes(msg.data[:msg.count])
        elif msg is None:  # poll for more output
            m.mav.serial_control_send(10, flags, 0, 0, 0, [0] * 70)
    m.mav.serial_control_send(10, 0, 0, 0, 0, [0] * 70)  # release the shell
    return out.decode(errors="replace")


def main():
    port, _ = pick_port(sys.argv[1] if len(sys.argv) > 1 else None)
    print(f"\n=== MAVLink on {port} ===")
    m = mavutil.mavlink_connection(port, baud=115200, source_system=255, source_component=190)
    hb = m.wait_heartbeat(timeout=15)
    if hb is None:
        sys.exit("No heartbeat in 15 s. If the board was just plugged in it may still be in its "
                 "bootloader; wait 10 s and run again.")
    autopilot = {3: "ArduPilot", 12: "PX4"}.get(hb.autopilot, f"autopilot id {hb.autopilot}")
    print(f"Heartbeat from system {m.target_system}, component {m.target_component}: {autopilot}, "
          f"vehicle type {hb.type}")

    statustext = []
    m.mav.command_long_send(m.target_system, m.target_component,
                            mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE, 0,
                            mavutil.mavlink.MAVLINK_MSG_ID_AUTOPILOT_VERSION, 0, 0, 0, 0, 0, 0)
    m.mav.command_long_send(m.target_system, m.target_component,
                            mavutil.mavlink.MAV_CMD_REQUEST_AUTOPILOT_CAPABILITIES, 0,
                            1, 0, 0, 0, 0, 0, 0)
    if hb.autopilot == 3:  # ArduPilot prints board name and UID in its banner
        m.mav.command_long_send(m.target_system, m.target_component,
                                mavutil.mavlink.MAV_CMD_DO_SEND_BANNER, 0, 0, 0, 0, 0, 0, 0, 0)

    ver, end = None, time.time() + 8
    while time.time() < end:
        msg = m.recv_match(type=["AUTOPILOT_VERSION", "STATUSTEXT"], blocking=True, timeout=1)
        if msg is None:
            continue
        if msg.get_type() == "STATUSTEXT":
            statustext.append(msg.text)
        elif ver is None:
            ver = msg

    print("\n=== AUTOPILOT_VERSION ===")
    if ver is None:
        print("Not received.")
    else:
        print(f"Firmware:       {fw_version(ver.flight_sw_version)}")
        print(f"Firmware git:   {bytes(ver.flight_custom_version).hex()}")
        print(f"Board version:  0x{ver.board_version:08X}")
        print(f"Vendor/product: 0x{ver.vendor_id:04X} / 0x{ver.product_id:04X}")
        print(f"UID (64-bit):   {ver.uid:016X}")
        uid2 = bytes(ver.uid2) if hasattr(ver, "uid2") else b""
        print(f"UID2 (18-byte): {uid2.hex().upper() if any(uid2) else '(not sent)'}")

    print("\n=== STATUSTEXT ===")
    print("\n".join(statustext) if statustext else "(none)")

    if hb.autopilot == 12:
        print("\n=== PX4 shell: ver all ===")
        print(px4_shell(m, "ver all"))
    m.close()


if __name__ == "__main__":
    main()
