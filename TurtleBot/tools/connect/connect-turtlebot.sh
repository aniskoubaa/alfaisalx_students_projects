#!/usr/bin/env bash
# connect-turtlebot.sh - SSH helper for the lab TurtleBot 4 (macOS and Linux).
#
# The same menu and commands as TurtleBotConnect.exe (Windows). It automates the steps in
# TurtleBot/HOW-TO-CONNECT.md: find the robot, open a terminal on it, set up key login, read its
# status, stop the motion programs, copy a file, add an SSH config shortcut, fix a changed host key.
#
# Security: it never stores, reads or passes a password. ssh asks for passwords itself. Every ssh and scp
# call checks the robot against the host key built into this file (PINNED_HOST_KEY), so a device that is
# not the robot is refused before a password prompt appears.
# Files it writes: ~/.config/turtlebot-connect/last_host.txt and known_hosts (the pinned key), your key
# (option 3) and, only if you choose option 6, a block appended to ~/.ssh/config (after a backup).
#
# Usage: ./connect-turtlebot.sh [connect|find|status|stop|setup-key] [host] [--host H] [--user U] [--key K]
# Runs on the bash 3.2 that ships with macOS: no associative arrays, ${x,,}, mapfile or GNU-only flags.

VERSION=1.1.0
DEFAULT_USER=ubuntu
MDNS_NAME=turtlebot4.local
AP_ADDRESS=10.42.0.1
ALIAS_NAME=turtlebot4
GUIDE=TurtleBot/HOW-TO-CONNECT.md
SSH_PORT=22
PROBE_SECS=3

ROBOT_USER=$DEFAULT_USER
DEFAULT_KEY="$HOME/.ssh/turtlebot4_ed25519"
KEY=$DEFAULT_KEY
SSH_CONFIG="$HOME/.ssh/config"
KNOWN_HOSTS=""
STATE_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/turtlebot-connect"
LAST_HOST_FILE="$STATE_DIR/last_host.txt"
PIN_KNOWN_HOSTS="$STATE_DIR/known_hosts"
CURRENT_HOST=""
HOST_VERIFIED=0
MENU_MODE=0
RESOLVED=""
FOUND_HOST=""
ANSWER=""
KEYOPT=()

# The lab robot's SSH host key. It is public (not a secret). Every ssh and scp call made by this script
# accepts only this key, under the name PIN_ALIAS, from a known_hosts file the script writes itself.
# The maintainer reads it on the robot with  ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
# (fingerprint SHA256:P2rMsKzoIV+vsYEUViVNEFf9H8ORHn+qYbEhaTciyi4, checked on 2026-10-04).
# After the robot is reinstalled: update this line and PinnedHostKeyDefault in TurtleBotConnect.cs,
# rebuild the exe with build.cmd, and update the fingerprint in README.md and HOW-TO-CONNECT.md.
PINNED_HOST_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINezwwah6HhR6o0ONkI77+B+XmFckK7JhQHI1Fn1nyBb"
PIN_ALIAS=turtlebot4-lab
TRUST_NEW=0
HOSTKEY_OPTS=()
SSH_OPTIONS=()

# Read-only status script run on the robot. Identical to StatusScript in TurtleBotConnect.cs
# (it contains no double quotes, so the Windows version can pass it as one quoted argument).
read -r -d '' STATUS_SCRIPT <<'EOF'
echo '== Robot =='; echo Name: $(hostname), $(uptime -p); echo '== Wi-Fi address (wlan0) =='; ip -4 -br addr show wlan0 2>/dev/null || echo 'wlan0 not found'; echo '== Robot software and lidar =='; s=$(systemctl is-active turtlebot4.service 2>/dev/null); case $s in active) echo 'turtlebot4.service: running';; *) echo turtlebot4.service: NOT running, state: $s;; esac; if [ -e /dev/RPLIDAR ]; then echo 'Lidar USB (/dev/RPLIDAR): connected'; else echo 'Lidar USB (/dev/RPLIDAR): NOT found (check the lidar USB cable)'; fi; echo '== Battery and dock (asking ROS, this can take up to a minute) =='; source /etc/turtlebot4/setup.bash >/dev/null 2>&1; t=$(mktemp -d); timeout 45 ros2 topic echo --once /battery_state --field percentage >$t/b 2>/dev/null & timeout 45 ros2 topic echo --once /dock_status --field is_docked >$t/d 2>/dev/null & wait; b=$(head -n 1 $t/b); d=$(head -n 1 $t/d); rm -rf $t; case $b in '') echo 'Battery: no answer within 45 s';; *) echo Battery: $(echo $b | awk '{v=$1; if (v<=1) v=v*100; print int(v+0.5)}') %;; esac; case $d in True) echo 'Docked: yes (on the charging dock)';; False) echo 'Docked: no (off the dock)';; '') echo 'Docked: no answer within 45 s';; *) echo Docked: $d;; esac; case $b$d in '') echo 'ROS did not answer. If the robot started less than 2 minutes ago, wait and try again. Otherwise the Create 3 base may be stuck: see HOW-TO-CONNECT.md, Restart the Create 3 base application.';; esac
EOF

# Emergency stop run on the robot. Identical to StopCommand in TurtleBotConnect.cs. The [x] in each
# pattern matches the same programs as the plain name, but stops pkill -f from matching (and killing)
# the remote shell that runs this command, whose own command line contains the patterns.
read -r -d '' STOP_COMMAND <<'EOF'
touch ~/STOP; pkill -INT -f 'motion_shape[s].py'; pkill -INT -f 'more_shape[s].py'; pkill -INT -f 'wall_approac[h].py'; pkill -INT -f 'keep_distanc[e].py'; pkill -TERM -f 'campaig[n].sh'; pkill -INT -f 'ros2 action send_goa[l]'; echo STOP-SENT
EOF

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_CYAN=$'\033[36m'
  C_DIM=$'\033[2m'; C_BOLD=$'\033[1m'; C_OFF=$'\033[0m'
else
  C_RED=; C_GREEN=; C_YELLOW=; C_CYAN=; C_DIM=; C_BOLD=; C_OFF=
fi

info() { printf '%s\n' "$*"; }
good() { printf '%s%s%s\n' "$C_GREEN" "$*" "$C_OFF"; }
warn() { printf '%s%s%s\n' "$C_YELLOW" "$*" "$C_OFF"; }
fail() { printf '%s%s%s\n' "$C_RED" "$*" "$C_OFF"; }
title() { printf '%s%s%s\n' "$C_CYAN" "$*" "$C_OFF"; }
show_cmd() { printf '    %s%s%s\n' "$C_DIM" "$*" "$C_OFF"; }

trim() {
  local s=$1
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "$s"
}

strip_quotes() {
  local s
  s=$(trim "$1")
  case $s in
    \"*\") s=${s#\"}; s=${s%\"} ;;
    \'*\') s=${s#\'}; s=${s%\'} ;;
  esac
  trim "$s"
}

# ask "prompt": the trimmed answer goes to ANSWER; returns 1 at end of input.
ask() {
  printf '%s%s%s' "$C_BOLD" "$1" "$C_OFF"
  if ! IFS= read -r ANSWER && [ -z "$ANSWER" ]; then
    ANSWER=""
    printf '\n'
    return 1
  fi
  [ -t 0 ] || printf '%s\n' "$ANSWER"   # echo piped input so logs read naturally
  ANSWER=$(trim "$ANSWER")
  return 0
}

ask_yes_no() {
  ask "$1" || return 1
  case $ANSWER in y|Y|yes|YES|Yes) return 0 ;; esac
  return 1
}

usage_error() {
  fail "$1"
  info "Run  ./connect-turtlebot.sh --help  for the list of commands."
  exit 2
}

print_help() {
  cat <<EOF
TurtleBot Connect $VERSION - open a terminal on the lab TurtleBot 4 over SSH.

Usage:
  ./connect-turtlebot.sh                    menu
  ./connect-turtlebot.sh connect [host]     find the robot and open a terminal on it
  ./connect-turtlebot.sh find               look for the robot and print its address
  ./connect-turtlebot.sh status [host]      print the robot's status (read only, up to a minute)
  ./connect-turtlebot.sh stop [host]        EMERGENCY: stop the motion programs on the robot
  ./connect-turtlebot.sh setup-key [host]   create your key and install it on the robot (one time)

Options:
  --host <address>   robot name or address. Without it the script tries the last address
                     that worked, then $MDNS_NAME, then $AP_ADDRESS.
  --user <name>      login name on the robot (default: $DEFAULT_USER)
  --key <path>       private key file (default: ~/.ssh/turtlebot4_ed25519)
  --trust-new-host-key
                     do not check the robot against the host key built into this script;
                     ssh asks instead. Only after the lab maintainer confirms the robot was
                     reinstalled and this script has not been updated yet.
  --help             show this text
  --version          show the version

Exit codes: 0 OK, 1 robot not found, 2 ssh missing or usage error, other: exit code of ssh.
The robot must present the SSH host key built into this script, fingerprint
  $(pinned_fingerprint);
any other device is refused before a password prompt appears.
Passwords are never stored: ssh asks for them itself. Full guide: $GUIDE
EOF
}

valid_host() {
  case $1 in
    ''|[![:alnum:]]*|*[![:alnum:]._:-]*) return 1 ;;
  esac
  [ ${#1} -le 253 ]
}

# Accepts "10.87.10.205", "turtlebot4.local", "ubuntu@10.42.0.1", "ssh ubuntu@x", "[fe80::1]".
normalize_host() {
  local s
  s=$(strip_quotes "$1")
  case $s in "ssh "*|"SSH "*) s=$(trim "${s#???}") ;; esac
  s=${s##*@}
  s=${s%/}
  case $s in \[*\]) s=${s#\[}; s=${s%\]} ;; esac
  valid_host "$s" || return 1
  printf '%s' "$s"
}

require_ssh() {
  command -v ssh >/dev/null 2>&1 && return 0
  fail "ssh (the OpenSSH client) was not found."
  info "macOS includes it. On Linux install it, for example:"
  show_cmd "sudo apt install openssh-client     (Ubuntu, Debian)"
  show_cmd "sudo dnf install openssh-clients    (Fedora)"
  return 1
}

key_opts() {
  KEYOPT=()
  if [ -f "$KEY" ]; then KEYOPT=(-i "$KEY"); fi
}

# ------------------------------------------------------------------ host key pinning

# Writes the script's own known_hosts file (one line: the pinned key under PIN_ALIAS) if it differs.
ensure_pin_file() {
  local want="$PIN_ALIAS $PINNED_HOST_KEY"
  [ -f "$PIN_KNOWN_HOSTS" ] && [ "$(cat "$PIN_KNOWN_HOSTS" 2>/dev/null)" = "$want" ] && return 0
  mkdir -p "$STATE_DIR" 2>/dev/null && printf '%s\n' "$want" > "$PIN_KNOWN_HOSTS" 2>/dev/null && return 0
  fail "Could not write $PIN_KNOWN_HOSTS."
  return 1
}

# A path as ssh expects it in an option or config file: ~/... when under $HOME, quoted if it has a space.
ssh_path_value() {
  local p=$1
  case $p in "$HOME"/*) p="~/${p#"$HOME"/}" ;; esac
  case $p in *" "*) p="\"$p\"" ;; esac
  printf '%s' "$p"
}

# Fills HOSTKEY_OPTS (accept only the pinned robot key, or ask with --trust-new-host-key) and SSH_OPTIONS.
host_key_opts() {
  if [ "$TRUST_NEW" = 1 ]; then
    HOSTKEY_OPTS=(-o StrictHostKeyChecking=ask)
    [ -n "$KNOWN_HOSTS" ] && HOSTKEY_OPTS=("${HOSTKEY_OPTS[@]}" -o "UserKnownHostsFile=$(ssh_path_value "$KNOWN_HOSTS")")
  else
    ensure_pin_file
    HOSTKEY_OPTS=(-o "HostKeyAlias=$PIN_ALIAS" -o "UserKnownHostsFile=$(ssh_path_value "$PIN_KNOWN_HOSTS")"
                  -o StrictHostKeyChecking=yes -o HostKeyAlgorithms=ssh-ed25519 -o CheckHostIP=no)
  fi
  SSH_OPTIONS=(-o ConnectTimeout=8 -o ServerAliveInterval=15 "${HOSTKEY_OPTS[@]}")
}

hk_shown() {   # the host key options as shown to the user (they are long and the same every time)
  if [ "$TRUST_NEW" = 1 ]; then printf '%s' "${HOSTKEY_OPTS[*]}"; else printf '%s' "[robot host key check]"; fi
}

pinned_fingerprint() {
  local fp
  fp=$(printf '%s %s\n' "$PIN_ALIAS" "$PINNED_HOST_KEY" | ssh-keygen -lf - 2>/dev/null | awk '{ print $2; exit }')
  printf '%s' "${fp:-(unknown)}"
}

# After ssh failed: asks ssh again, without any password prompt, whether the host key was the problem.
host_key_mismatch() {   # target
  local err
  [ "$TRUST_NEW" = 1 ] && return 1
  host_key_opts
  key_opts
  err=$(ssh -n -o BatchMode=yes -o ConnectTimeout=5 "${HOSTKEY_OPTS[@]}" "${KEYOPT[@]}" "$1" true 2>&1 >/dev/null)
  case $err in
    *"REMOTE HOST IDENTIFICATION HAS CHANGED"*|*"Host key verification failed"*|*"no matching host key type"*|*"host key is known"*) return 0 ;;
  esac
  return 1
}

handle_ssh_failure() {   # host
  if host_key_mismatch "$ROBOT_USER@$1"; then print_host_key_mismatch "$1"; else print_ssh_failure_hints; fi
}

print_host_key_mismatch() {   # host
  fail "The device at $1 is not the lab robot as this script knows it: its SSH host key is not the"
  fail "built-in robot key. ssh stopped before asking for any password, so nothing was sent."
  info "Either this address is not the lab robot (another device on the network), or the robot was reinstalled."
  info "Ask the lab maintainer. If the robot was reinstalled, the pinned key in this script must be updated"
  info "(README.md in this script's folder, section Host key pinning)."
  info "Expected fingerprint: $(pinned_fingerprint)"
  info "Do not edit $PIN_KNOWN_HOSTS: the script rewrites it."
  info "Only if the maintainer confirms a reinstall and no updated script exists yet: run the script with"
  info "--trust-new-host-key, and continue only if the fingerprint ssh shows is the one the maintainer reads on the robot."
}

print_trust_new_warning() {
  warn "--trust-new-host-key: the robot's identity is NOT checked against the built-in host key."
  warn "If ssh asks whether to trust the robot, continue only if the fingerprint it shows is the one the lab"
  warn "maintainer read on the robot (ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub). The key built into"
  warn "this script has fingerprint $(pinned_fingerprint); you can paste the expected fingerprint at ssh's prompt."
}

# ------------------------------------------------------------------ finding the robot

NC_Z=""
detect_nc() {   # use nc only if this nc supports -z (some ncat versions do not)
  [ -n "$NC_Z" ] && return
  NC_Z=no
  if command -v nc >/dev/null 2>&1 && nc -h 2>&1 | grep -q -- '-z'; then NC_Z=yes; fi
}

probe_port() {   # host port seconds -> 0 if the TCP port answers within the time
  local h=$1 p=$2 t=$3 pid killer rc
  detect_nc
  if [ "$NC_Z" = yes ]; then
    nc -z -w "$t" "$h" "$p" >/dev/null 2>&1 &
  else
    ( exec 3<>"/dev/tcp/$h/$p" ) >/dev/null 2>&1 &
  fi
  pid=$!
  # macOS has no 'timeout' command: a background timer kills the probe instead.
  ( sleep "$t"; kill "$pid" 2>/dev/null ) >/dev/null 2>&1 &
  killer=$!
  wait "$pid" 2>/dev/null
  rc=$?
  kill "$killer" 2>/dev/null
  wait "$killer" 2>/dev/null
  return $rc
}

load_last_host() {
  local h=""
  [ -f "$LAST_HOST_FILE" ] && h=$(trim "$(head -n 1 "$LAST_HOST_FILE" 2>/dev/null)")
  valid_host "$h" && printf '%s' "$h"
}

save_last_host() {
  mkdir -p "$STATE_DIR" 2>/dev/null && printf '%s\n' "$1" > "$LAST_HOST_FILE" 2>/dev/null
  return 0
}

set_current() {
  CURRENT_HOST=$1
  HOST_VERIFIED=1
  save_last_host "$1"
}

# search_hosts LAST host...: probes all hosts in parallel, sets FOUND_HOST to the first one (in list
# order) whose SSH port answered. LAST is the remembered address (for the label) or "".
search_hosts() {
  local last=$1 tmp i h r label
  shift
  FOUND_HOST=""
  detect_nc
  tmp=$(mktemp -d 2>/dev/null || mktemp -d -t tbconnect) || return 1
  i=0
  for h in "$@"; do
    ( if probe_port "$h" "$SSH_PORT" "$PROBE_SECS"; then echo ok; else echo no; fi ) > "$tmp/$i" 2>/dev/null &
    i=$((i + 1))
  done
  wait
  i=0
  for h in "$@"; do
    r=$(cat "$tmp/$i" 2>/dev/null)
    label=$h
    [ -n "$last" ] && [ "$h" = "$last" ] && label="$h (last used)"
    if [ "$r" = ok ] && [ -z "$FOUND_HOST" ]; then
      FOUND_HOST=$h
      good "$(printf '  %-32s' "$label")answered on port $SSH_PORT"
    elif [ "$r" = ok ]; then
      info "$(printf '  %-32s' "$label")answered too (not needed)"
    else
      info "$(printf '  %-32s' "$label")no answer"
    fi
    i=$((i + 1))
  done
  rm -rf "$tmp"
  [ -n "$FOUND_HOST" ]
}

search_robot() {
  local last
  last=$(load_last_host)
  info "Looking for the robot (this takes up to 6 seconds)..."
  if [ -n "$last" ] && [ "$last" != "$MDNS_NAME" ] && [ "$last" != "$AP_ADDRESS" ]; then
    search_hosts "$last" "$last" "$MDNS_NAME" "$AP_ADDRESS"
  else
    search_hosts "$last" "$MDNS_NAME" "$AP_ADDRESS"
  fi || return 1
  set_current "$FOUND_HOST"
}

probe_single() {
  info "Checking $1 ..."
  search_hosts "" "$1" || return 1
  set_current "$1"
}

local_ipv4() {
  if command -v ip >/dev/null 2>&1; then
    ip -4 -o addr show 2>/dev/null | awk '$2 != "lo" { a = $4; sub(/\/.*/, "", a); print $2 ": " a }'
  elif command -v ifconfig >/dev/null 2>&1; then
    ifconfig 2>/dev/null | awk '/^[^ \t]/ { iface = $1; sub(/:$/, "", iface) }
      $1 == "inet" { a = $2; sub(/^addr:/, "", a); if (a != "127.0.0.1") print iface ": " a }'
  elif command -v ipconfig >/dev/null 2>&1; then
    ipconfig 2>/dev/null | tr -d '\r' | awk -F': ' '/IPv4/ { print "IPv4: " $2 }'
  fi
}

print_not_found() {   # $1 = 1 when the user can type an address next
  local addrs on_ap=0 line
  fail "The robot did not answer."
  info "This computer's network addresses (IPv4):"
  addrs=$(local_ipv4)
  if [ -z "$addrs" ]; then
    info "  none found (not connected, or no 'ip'/'ifconfig' command)"
  else
    while IFS= read -r line; do
      info "  $line"
      case $line in *": 10.42.0."*) on_ap=1 ;; esac
    done <<EOF
$addrs
EOF
  fi
  if [ "$on_ap" = 1 ]; then
    warn "You are on the robot's own Wi-Fi (10.42.0.x), but 10.42.0.1 did not answer."
    warn "The robot may still be starting: wait about 2 minutes after the chime and try again."
  fi
  info "What to do:"
  info "  1. Check that the robot sits on its dock and is on. After it starts, wait about 2 minutes:"
  info "     it plays a chime and shows its address on the display."
  info "  2. Display shows 10.87.x.x: join the 'Students' Wi-Fi on this computer, then try again"
  info "     (the script uses the name $MDNS_NAME)."
  info "  3. Display shows 10.42.0.1: join the robot's own Wi-Fi 'Turtlebot4' (it has no internet),"
  info "     then try again."
  if [ "$1" = 1 ]; then
    info "  4. Otherwise type the address shown on the robot's display below."
  else
    info "  4. Otherwise give the address from the display, for example:  ./connect-turtlebot.sh connect 10.87.10.205"
  fi
  info "  More help: $GUIDE, section Troubleshooting."
}

ask_for_address() {   # sets RESOLVED; returns 1 if the user gave up
  local h
  while true; do
    ask "Type the robot's address from its display (or press Enter to go back): " || return 1
    [ -z "$ANSWER" ] && return 1
    if ! h=$(normalize_host "$ANSWER"); then
      warn "That does not look like an address. Example: 10.87.10.205"
      continue
    fi
    if probe_single "$h"; then RESOLVED=$h; return 0; fi
    warn "No answer from $h. Check the address on the display, and that this computer is on the same Wi-Fi."
  done
}

# resolve_host HOST_ARG INTERACTIVE: sets RESOLVED to the host to use; returns 1 if not reachable.
resolve_host() {
  local arg=$1 interactive=$2
  RESOLVED=""
  if [ -n "$arg" ]; then
    if probe_single "$arg"; then RESOLVED=$arg; return 0; fi
    print_not_found "$interactive"
    [ "$interactive" = 1 ] && ask_for_address && return 0
    return 1
  fi
  if [ -n "$CURRENT_HOST" ]; then
    if [ "$HOST_VERIFIED" = 1 ]; then RESOLVED=$CURRENT_HOST; return 0; fi
    if probe_single "$CURRENT_HOST"; then RESOLVED=$CURRENT_HOST; return 0; fi
    warn "No answer from $CURRENT_HOST; searching the usual addresses instead."
    CURRENT_HOST=""
  fi
  if search_robot; then RESOLVED=$CURRENT_HOST; return 0; fi
  print_not_found "$interactive"
  [ "$interactive" = 1 ] && ask_for_address && return 0
  return 1
}

do_find() {   # $1 = host or ""
  local ok=1
  if [ -n "$1" ]; then probe_single "$1" && ok=0; else search_robot && ok=0; fi
  if [ "$ok" != 0 ]; then
    print_not_found 0
    return 1
  fi
  good "Robot found: $CURRENT_HOST"
  info "Open a terminal on it:  ./connect-turtlebot.sh connect   (or: ssh $ROBOT_USER@$CURRENT_HOST)"
  return 0
}

menu_find() {
  CURRENT_HOST=""
  HOST_VERIFIED=0
  if search_robot; then
    good "Robot found: $CURRENT_HOST. Choose 1 to open a terminal on it."
    return 0
  fi
  print_not_found 1
  ask_for_address && good "Robot found: $RESOLVED. Choose 1 to open a terminal on it."
}

print_ssh_failure_hints() {
  fail "ssh could not connect or log in (exit code 255). Read the ssh message above:"
  info "  'Permission denied': wrong password, or your key is not installed (menu option 3, or setup-key)."
  info "  'Host key verification failed' or 'REMOTE HOST IDENTIFICATION HAS CHANGED': the device at that"
  info "  address is not the lab robot, or the robot was reinstalled. Ask the lab maintainer (menu option 9 explains)."
  info "  'Connection timed out' or 'Could not resolve hostname': the robot or this computer changed"
  info "  network. Search again (menu option 2, or the find command)."
}

# ------------------------------------------------------------------ 1) connect

do_connect() {   # host_arg interactive
  local target rc
  resolve_host "$1" "$2" || return 1
  target="$ROBOT_USER@$RESOLVED"
  key_opts
  host_key_opts || return 2
  good "Opening a terminal on the robot ($target)."
  if [ "$MENU_MODE" = 1 ]; then
    info "Type  exit  (or press Ctrl+D) to log out and come back to this menu."
  else
    info "Type  exit  (or press Ctrl+D) to log out."
  fi
  if [ -f "$KEY" ]; then
    info "Using your key $KEY. If a password is still asked for, the key is not installed yet (option 3 / setup-key)."
  else
    info "When asked, type the robot's '$ROBOT_USER' password. Nothing shows while you type; that is normal."
  fi
  show_cmd "ssh -t -o ConnectTimeout=8 -o ServerAliveInterval=15 $(hk_shown) ${KEYOPT[*]} $target"
  ssh -t "${SSH_OPTIONS[@]}" "${KEYOPT[@]}" "$target"
  rc=$?
  if [ "$rc" = 255 ]; then handle_ssh_failure "$RESOLVED"; else info "Disconnected from the robot."; fi
  return $rc
}

# ------------------------------------------------------------------ 3) key login

key_comment() {
  local u h
  u=$(id -un 2>/dev/null || echo user)
  h=$(hostname 2>/dev/null || uname -n)
  u=$(printf '%s' "$u" | LC_ALL=C tr -c 'A-Za-z0-9._-' '_')
  h=$(printf '%s' "$h" | LC_ALL=C tr -c 'A-Za-z0-9._-' '_')
  printf 'turtlebot4-%s@%s' "${u:-user}" "${h:-pc}"
}

key_has_passphrase() {
  ! ssh-keygen -y -P '' -f "$KEY" >/dev/null 2>&1
}

key_login_works() {   # target
  host_key_opts
  ssh -n -o BatchMode=yes -o ConnectTimeout=8 "${HOSTKEY_OPTS[@]}" -i "$KEY" "$1" true >/dev/null 2>&1
}

print_key_explanation() {   # comment base64
  local tail16=${2:$((${#2} - 16))}
  info "Each lab member adds their own key this way; never share or copy key files."
  info "The private key $KEY stays on this computer only. Never commit it to a repository."
  info "To remove this computer's access later: log in to the robot, open ~/.ssh/authorized_keys"
  info "(for example  nano ~/.ssh/authorized_keys ) and delete the one line that contains"
  info "  $tail16   (when this program added it, the line ends with $1),"
  info "then delete $KEY and $KEY.pub on this computer."
}

do_setup_key() {   # host_arg interactive
  local comment ktype kb64 rest target remote rc keydir has_pp=0
  comment=$(key_comment)
  title "Set up key login (one time per computer)"
  if [ ! -f "$KEY" ]; then
    info "Step 1: create your personal key at $KEY"
    info "A passphrase protects the key if this computer is lost or shared, but you then type the passphrase"
    info "at each login instead of the robot password. Without one, anyone who copies the key file can log in."
    keydir=$(dirname "$KEY")
    mkdir -p "$keydir" || return 2
    [ "$keydir" = "$HOME/.ssh" ] && chmod 700 "$keydir"
    if ask_yes_no "Protect the key with a passphrase? (y/N): "; then
      info "ssh-keygen now asks for the passphrase twice (nothing shows while you type)."
      show_cmd "ssh-keygen -t ed25519 -f $KEY -C $comment"
      ssh-keygen -t ed25519 -f "$KEY" -C "$comment"
    else
      show_cmd "ssh-keygen -t ed25519 -f $KEY -C $comment -N ''"
      ssh-keygen -t ed25519 -f "$KEY" -C "$comment" -N ''
    fi
    rc=$?
    if [ "$rc" != 0 ] || [ ! -f "$KEY" ] || [ ! -f "$KEY.pub" ]; then
      fail "Creating the key failed (ssh-keygen exit code $rc)."
      return 2
    fi
    good "Key created: $KEY (private, stays on this computer) and $KEY.pub."
  else
    info "Step 1: you already have a key: $KEY"
  fi
  if [ ! -f "$KEY.pub" ]; then
    fail "The public key $KEY.pub is missing. Delete $KEY and run this again."
    return 2
  fi
  read -r ktype kb64 rest < "$KEY.pub"
  kb64=${kb64%$'\r'}
  case $ktype in ssh-ed25519*) ;; *) ktype="" ;; esac
  case $ktype in *[!A-Za-z0-9@.-]*) ktype="" ;; esac
  case $kb64 in ''|*[!A-Za-z0-9+/=]*) kb64="" ;; esac
  if [ -z "$ktype" ] || [ ${#kb64} -lt 20 ]; then
    fail "The public key $KEY.pub is not an ed25519 key (it should start with ssh-ed25519)."
    return 2
  fi

  info "Step 2: install the public key on the robot."
  if ! resolve_host "$1" "$2"; then
    warn "The key is ready on this computer. Install it later with setup-key (menu option 3) when the robot answers."
    return 1
  fi
  target="$ROBOT_USER@$RESOLVED"
  key_has_passphrase && has_pp=1
  if [ "$has_pp" = 0 ] && key_login_works "$target"; then
    good "Key login already works for $target. Nothing to install."
    print_key_explanation "$comment" "$kb64"
    return 0
  fi
  remote="mkdir -p ~/.ssh && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && (grep -qF '$kb64' ~/.ssh/authorized_keys || echo '$ktype $kb64 $comment' >> ~/.ssh/authorized_keys) && echo KEY-OK"
  info "Type the robot's '$ROBOT_USER' password when ssh asks (nothing shows while you type). This is the last time you need it here."
  show_cmd "ssh -t ... $target \"<add your public key to ~/.ssh/authorized_keys>\""
  host_key_opts || return 2
  ssh -t -o ConnectTimeout=8 "${HOSTKEY_OPTS[@]}" "$target" "$remote"
  rc=$?
  if [ "$rc" != 0 ]; then
    fail "Installing the key failed (ssh exit code $rc)."
    [ "$rc" = 255 ] && handle_ssh_failure "$RESOLVED"
    return $rc
  fi

  info "Step 3: check that the key works."
  if [ "$has_pp" = 1 ]; then
    info "Type your key passphrase when asked (not the robot password)."
    ssh -o ConnectTimeout=8 "${HOSTKEY_OPTS[@]}" -o PreferredAuthentications=publickey \
        -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no -i "$KEY" "$target" true
    rc=$?
  else
    if key_login_works "$target"; then rc=0; else rc=255; fi
  fi
  if [ "$rc" != 0 ]; then
    fail "The key was copied but logging in with it failed (exit code $rc)."
    info "Ask the lab maintainer to check ~/.ssh on the robot (it must not be writable by others)."
    return $rc
  fi
  good "Key login works. Connect (option 1) no longer asks for the robot password."
  print_key_explanation "$comment" "$kb64"
  return 0
}

# ------------------------------------------------------------------ 4) status

do_status() {   # host_arg interactive
  local target rc
  resolve_host "$1" "$2" || return 1
  target="$ROBOT_USER@$RESOLVED"
  key_opts
  host_key_opts || return 2
  info "Asking the robot for its status (read only). The battery and dock part asks ROS and can take up to a minute."
  show_cmd "ssh -o ConnectTimeout=8 -o ServerAliveInterval=15 $(hk_shown) ${KEYOPT[*]} $target \"<read-only status commands>\""
  ssh "${SSH_OPTIONS[@]}" "${KEYOPT[@]}" "$target" "$STATUS_SCRIPT"
  rc=$?
  [ "$rc" = 255 ] && handle_ssh_failure "$RESOLVED"
  return $rc
}

# ------------------------------------------------------------------ 5) VS Code

alias_hostname() {   # prints the HostName of the 'Host turtlebot4' block; exit 1 if there is no such block
  [ -f "$SSH_CONFIG" ] || return 1
  awk -v alias="$ALIAS_NAME" '
    { sub(/\r$/, ""); gsub(/=/, " ") }
    tolower($1) == "host" || tolower($1) == "match" {
      inb = 0
      if (tolower($1) == "host") for (i = 2; i <= NF; i++) if (tolower($i) == alias) { inb = 1; found = 1 }
      next
    }
    inb && tolower($1) == "hostname" && name == "" { name = $2 }
    END { if (!found) exit 1; print name }
  ' "$SSH_CONFIG"
}

print_alias_block() {
  awk -v alias="$ALIAS_NAME" '
    { line = $0; sub(/\r$/, "", line); n = split(line, f, /[ \t=]+/); k = (f[1] == "" ? 2 : 1) }
    tolower(f[k]) == "host" || tolower(f[k]) == "match" {
      inb = 0
      if (tolower(f[k]) == "host") for (i = k + 1; i <= n; i++) if (tolower(f[i]) == alias) inb = 1
    }
    inb && line ~ /[^ \t]/ { print "    " line }
  ' "$SSH_CONFIG"
}

do_vscode() {
  local remote ahost folder
  if ! command -v code >/dev/null 2>&1; then
    warn "VS Code was not found (no 'code' command)."
    info "Install VS Code from https://code.visualstudio.com/ . On macOS, open VS Code, press Cmd+Shift+P and run"
    info "'Shell Command: Install code command in PATH'. Then add Microsoft's 'Remote - SSH' extension."
    info "Steps: $GUIDE, section Write and run code, Option A."
    return 2
  fi
  resolve_host "" 1 || return 1
  remote="$ROBOT_USER@$RESOLVED"
  if ahost=$(alias_hostname); then
    ahost=${ahost:-$ALIAS_NAME}
    # The shortcut works if its HostName is where the robot answered, or answers itself
    # (for example turtlebot4.local while the robot was found by its 10.87 address).
    if [ "$(printf '%s' "$ahost" | tr '[:upper:]' '[:lower:]')" = "$(printf '%s' "$RESOLVED" | tr '[:upper:]' '[:lower:]')" ] \
       || probe_port "$ahost" "$SSH_PORT" "$PROBE_SECS"; then
      remote=$ALIAS_NAME
      info "Using your '$ALIAS_NAME' shortcut from $SSH_CONFIG (it uses your key)."
    else
      warn "Your '$ALIAS_NAME' shortcut points to $ahost, which did not answer (the robot answered at $RESOLVED). Edit HostName in $SSH_CONFIG to use the shortcut."
    fi
  fi
  if [ "$remote" != "$ALIAS_NAME" ]; then
    info "Without the SSH config shortcut (option 6, plus key login from option 3), VS Code asks for the"
    info "robot password, sometimes more than once."
  fi
  info "VS Code needs Microsoft's 'Remote - SSH' extension. If it asks for the platform, choose Linux."
  info "The first connection installs the VS Code server on the robot (about 200 MB; up to 10 minutes on campus Wi-Fi)."
  info "Recommended settings: $GUIDE, Option A."
  folder="/home/$ROBOT_USER/robot_code"
  show_cmd "code --remote ssh-remote+$remote $folder"
  if code --remote "ssh-remote+$remote" "$folder"; then
    good "VS Code is opening. Its window shows the connection progress."
    return 0
  fi
  fail "Could not start VS Code."
  return 2
}

# ------------------------------------------------------------------ 6) SSH config shortcut

identity_file_value() {
  if [ "$KEY" = "$DEFAULT_KEY" ]; then printf '%s' "~/.ssh/turtlebot4_ed25519"; return; fi
  case $KEY in *" "*) printf '"%s"' "$KEY" ;; *) printf '%s' "$KEY" ;; esac
}

do_ssh_config() {
  local host block backup prefix="" dir have_key=0
  if alias_hostname >/dev/null 2>&1; then
    good "Your SSH config already has a 'Host $ALIAS_NAME' entry. Nothing was changed."
    print_alias_block
    info "To change it, edit $SSH_CONFIG yourself."
    return 0
  fi
  host=$CURRENT_HOST
  if [ -z "$host" ]; then
    if search_robot; then
      host=$CURRENT_HOST
    else
      host=$MDNS_NAME
      warn "The robot did not answer, so the shortcut uses the name $MDNS_NAME (works on 'Students' and on"
      warn "the robot's own Wi-Fi). Change HostName in the file later if the name does not work."
    fi
  fi
  [ -f "$KEY" ] && have_key=1
  block="Host $ALIAS_NAME
    HostName $host
    User $ROBOT_USER"
  [ "$have_key" = 1 ] && block="$block
    IdentityFile $(identity_file_value)"
  if [ "$TRUST_NEW" = 1 ]; then
    # Pinning is switched off for this run (robot reinstalled, script not updated yet): no pinned lines.
    block="$block
    StrictHostKeyChecking ask"
  else
    # Same protection as the script's own ssh calls: only the pinned robot key is accepted.
    ensure_pin_file || return 2
    block="$block
    HostKeyAlias $PIN_ALIAS
    UserKnownHostsFile ~/.ssh/known_hosts $(ssh_path_value "$PIN_KNOWN_HOSTS")
    StrictHostKeyChecking yes
    HostKeyAlgorithms ssh-ed25519"
  fi
  block="$block
    ConnectTimeout 8"
  dir=$(dirname "$SSH_CONFIG")
  if [ ! -d "$dir" ]; then
    mkdir -p "$dir" || return 2
    [ "$dir" = "$HOME/.ssh" ] && chmod 700 "$dir"
  fi
  if [ -f "$SSH_CONFIG" ]; then
    backup="$SSH_CONFIG.bak-$(date +%Y%m%d-%H%M%S)"
    cp -p "$SSH_CONFIG" "$backup" || { fail "Could not back up $SSH_CONFIG. Nothing was changed."; return 2; }
    info "Backup of your current file: $backup"
    if [ -s "$SSH_CONFIG" ]; then
      [ -n "$(tail -c 1 "$SSH_CONFIG")" ] && prefix=$'\n'
      prefix="$prefix"$'\n'
    fi
  else
    ( umask 077; : > "$SSH_CONFIG" ) || return 2
  fi
  printf '%s%s\n' "$prefix" "$block" >> "$SSH_CONFIG" || { fail "Could not write $SSH_CONFIG."; return 2; }
  good "Added this block to the end of $SSH_CONFIG (existing lines were not changed):"
  printf '%s\n' "$block" | while IFS= read -r line; do show_cmd "$line"; done
  info "Now you can type  ssh $ALIAS_NAME  and  scp myfile.py $ALIAS_NAME:robot_code/ , and VS Code lists"
  info "'$ALIAS_NAME' under Remote Explorer."
  [ "$have_key" = 0 ] && warn "No key yet: after option 3, add the line  IdentityFile ~/.ssh/turtlebot4_ed25519  to the block."
  case $host in 10.87.*)
    warn "10.87.x.x addresses come from the university Wi-Fi and can change. If 'ssh $ALIAS_NAME' stops working, set HostName to $MDNS_NAME or the new address." ;;
  esac
  return 0
}

# ------------------------------------------------------------------ 7) emergency stop

do_stop() {   # host_arg interactive
  local target rc
  printf '%s%s%s\n' "$C_RED" "EMERGENCY STOP: telling the robot's motion programs to stop." "$C_OFF"
  printf '%s%s%s\n' "$C_RED" "If the robot is moving towards danger, pick it up now: the wheels stop when it is lifted." "$C_OFF"
  if ! resolve_host "$1" "$2"; then
    fail "Could not reach the robot. Pick it up (the Create 3 stops its wheels when lifted) or press the power button on the base."
    return 1
  fi
  target="$ROBOT_USER@$RESOLVED"
  key_opts
  host_key_opts || return 2
  [ -f "$KEY" ] || info "If asked, type the robot's '$ROBOT_USER' password."
  show_cmd "ssh $target \"$STOP_COMMAND\""
  ssh "${SSH_OPTIONS[@]}" "${KEYOPT[@]}" "$target" "$STOP_COMMAND"
  rc=$?
  if [ "$rc" = 0 ]; then
    good "STOP sent. A running motion program stops the wheels within a second."
    info "The file ~/STOP now blocks new runs of the motion programs. When it is safe to drive again,"
    info "log in and type:  rm ~/STOP"
    info "Picking the robot up always stops the wheels (wheel-drop safety on the Create 3)."
  else
    fail "Sending STOP failed (ssh exit code $rc). Pick the robot up: the wheels stop when it is lifted."
    [ "$rc" = 255 ] && handle_ssh_failure "$RESOLVED"
  fi
  return $rc
}

# ------------------------------------------------------------------ 8) copy a file

do_copy() {
  local p remote host rflag="" rc
  info "Copy a file (or a folder) from this computer into ~/robot_code on the robot."
  ask "Drag the file onto this window, or type its path, then press Enter: " || return 0
  [ -z "$ANSWER" ] && return 0
  p=$(strip_quotes "$ANSWER")
  case $p in "~/"*) p="$HOME/${p#\~/}" ;; esac
  if [ ! -e "$p" ]; then
    # macOS Terminal escapes spaces when a file is dropped: My\ File.py
    p=$(printf '%s' "$p" | sed 's/\\\(.\)/\1/g')
  fi
  if [ ! -e "$p" ]; then
    fail "Not found: $p"
    return 2
  fi
  [ -d "$p" ] && rflag=-r
  [ "$p" != "/" ] && p=${p%/}
  resolve_host "" 1 || return 1
  host=$RESOLVED
  case $host in *:*) host="[$host]" ;; esac
  remote="$ROBOT_USER@$host:robot_code/"
  key_opts
  host_key_opts || return 2
  show_cmd "scp -o ConnectTimeout=8 $(hk_shown) $rflag ${KEYOPT[*]} $p $remote"
  if [ -n "$rflag" ]; then
    scp -o ConnectTimeout=8 "${HOSTKEY_OPTS[@]}" -r "${KEYOPT[@]}" "$p" "$remote"
  else
    scp -o ConnectTimeout=8 "${HOSTKEY_OPTS[@]}" "${KEYOPT[@]}" "$p" "$remote"
  fi
  rc=$?
  if [ "$rc" = 0 ]; then
    good "Copied. On the robot it is in ~/robot_code/$(basename "$p")"
  else
    fail "Copy failed (scp exit code $rc). Check that ~/robot_code exists on the robot."
    host_key_mismatch "$ROBOT_USER@$RESOLVED" && print_host_key_mismatch "$RESOLVED"
  fi
  return $rc
}

# ------------------------------------------------------------------ 9) host key changed

do_fix_host_key() {
  local def host rc
  title "Fix 'WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!'"
  info "This script checks the robot's identity against the host key built into it:"
  info "  $(pinned_fingerprint)"
  info "A device with another key is refused before any password prompt. If that happens, either the address"
  info "is not the lab robot, or the robot was reinstalled and this script must be updated by the lab"
  info "maintainer (README.md in this script's folder, section Host key pinning). Nothing on this computer"
  info "needs fixing for that, and this option does not change it."
  echo
  info "Plain ssh (and VS Code without option 6) instead remembers each robot's identity in"
  info "~/.ssh/known_hosts and warns when it changes. This option removes the old entry there. That is expected"
  info "when the robot's SD card was reinstalled, or when the address now belongs to another device. It can also"
  info "mean another device is pretending to be the robot."
  warn "Continue only after the lab maintainer confirms the robot was reinstalled or its address changed."
  def=${CURRENT_HOST:-$MDNS_NAME}
  ask "Name or address shown in the warning [$def]: " || return 0
  if [ -z "$ANSWER" ]; then
    host=$def
  elif ! host=$(normalize_host "$ANSWER"); then
    warn "That does not look like a name or address. Nothing was changed."
    return 2
  fi
  ask "Type yes to forget the saved identity of $host: " || { info "Cancelled. Nothing was changed."; return 0; }
  if [ "$(printf '%s' "$ANSWER" | tr '[:upper:]' '[:lower:]')" != yes ]; then
    info "Cancelled. Nothing was changed."
    return 0
  fi
  if [ -n "$KNOWN_HOSTS" ]; then
    show_cmd "ssh-keygen -R $host -f $KNOWN_HOSTS"
    ssh-keygen -R "$host" -f "$KNOWN_HOSTS"
  else
    show_cmd "ssh-keygen -R $host"
    ssh-keygen -R "$host"
  fi
  rc=$?
  if [ "$rc" = 0 ]; then good "Done. The next plain ssh connection asks you to confirm the robot's new identity: compare its fingerprint with the lab maintainer's."; else fail "ssh-keygen failed (exit code $rc)."; fi
  return $rc
}

# ------------------------------------------------------------------ menu

print_menu() {
  local robot keyline
  if [ -z "$CURRENT_HOST" ]; then
    robot="not searched yet (option 1 or 2 finds it)"
  elif [ "$HOST_VERIFIED" = 1 ]; then
    robot="$CURRENT_HOST  (answered)"
  else
    robot="$CURRENT_HOST  (not checked yet)"
  fi
  if [ -f "$KEY" ]; then keyline=$KEY; else keyline="none yet (option 3 lets you log in without the password)"; fi
  echo
  title "===================================================="
  title "  TurtleBot Connect $VERSION   (lab TurtleBot 4)"
  title "===================================================="
  info "  Robot:  $robot"
  info "  Key:    $keyline"
  if [ "$TRUST_NEW" = 1 ]; then
    warn "  Robot identity: NOT checked (--trust-new-host-key). Compare fingerprints with the lab maintainer."
  else
    info "  Robot identity: checked against the built-in host key ($(pinned_fingerprint))"
  fi
  echo
  info "  1) Connect (open a robot terminal)"
  info "  2) Find the robot"
  info "  3) Set up key login (one time)"
  info "  4) Robot status (read only)"
  info "  5) Open in VS Code"
  info "  6) Add a 'turtlebot4' shortcut to my SSH config"
  printf '%s%s%s\n' "$C_RED" "  7) EMERGENCY: stop motion programs" "$C_OFF"
  info "  8) Copy a file to the robot"
  info "  9) Fix \"host key changed\""
  info "  0) Exit"
  echo
}

run_menu() {
  MENU_MODE=1
  require_ssh || exit 2
  # Ctrl+C while ssh runs ends ssh, not this menu.
  trap 'printf "\n"' INT
  while true; do
    print_menu
    ask "Choose a number and press Enter: " || exit 0
    case $ANSWER in
      1) do_connect "" 1 ;;
      2) menu_find ;;
      3) do_setup_key "" 1 ;;
      4) do_status "" 1 ;;
      5) do_vscode ;;
      6) do_ssh_config ;;
      7) do_stop "" 1 ;;
      8) do_copy ;;
      9) do_fix_host_key ;;
      0|q|Q|exit) exit 0 ;;
      *) warn "Please type a number from 0 to 9."; continue ;;
    esac
    if [ -t 0 ]; then ask "Press Enter to return to the menu..." || exit 0; fi
  done
}

# ------------------------------------------------------------------ command line

main() {
  local opt_host="" cmd="" host_arg="" v pk_type pk_b64
  local -a positional
  positional=()
  while [ $# -gt 0 ]; do
    case $1 in
      --help|-h|help) print_help; exit 0 ;;
      --version|-v) echo "connect-turtlebot.sh $VERSION"; exit 0 ;;
      --trust-new-host-key) TRUST_NEW=1; shift; continue ;;
      --host|--user|--key|--ssh-config|--known-hosts|--pinned-key)
        [ $# -ge 2 ] || usage_error "Missing value after $1."
        v=$2
        case $1 in
          --host) opt_host=$(normalize_host "$v") || usage_error "Not a valid robot name or address: $v" ;;
          --user)
            case $v in ''|[!A-Za-z_]*|*[!A-Za-z0-9_.-]*) usage_error "Not a valid user name: $v" ;; esac
            ROBOT_USER=$v ;;
          --key) KEY=$(strip_quotes "$v") ;;
          --ssh-config) SSH_CONFIG=$(strip_quotes "$v") ;;     # hidden: for testing
          --known-hosts) KNOWN_HOSTS=$(strip_quotes "$v") ;;   # hidden: for testing
          --pinned-key)   # hidden: pin another server's key, for testing against a test SSH server
            v=$(strip_quotes "$v")
            pk_type=${v%% *}
            pk_b64=${v#* }
            pk_b64=${pk_b64%% *}
            [ "$pk_type" = ssh-ed25519 ] || usage_error "--pinned-key needs \"ssh-ed25519 <base64>\"."
            case $pk_b64 in ''|*[!A-Za-z0-9+/=]*) usage_error "--pinned-key needs \"ssh-ed25519 <base64>\"." ;; esac
            PINNED_HOST_KEY="$pk_type $pk_b64" ;;
        esac
        shift 2
        continue ;;
      -*) usage_error "Unknown option: $1" ;;
      *) positional+=("$1"); shift ;;
    esac
  done

  if [ "$TRUST_NEW" = 1 ] && [ "$(printf '%s' "${positional[0]}" | tr '[:upper:]' '[:lower:]')" != find ]; then
    print_trust_new_warning
  fi
  if [ ${#positional[@]} -eq 0 ]; then
    if [ -n "$opt_host" ]; then CURRENT_HOST=$opt_host; HOST_VERIFIED=0; fi
    run_menu
  fi
  [ ${#positional[@]} -gt 2 ] && usage_error "Too many arguments."
  cmd=$(printf '%s' "${positional[0]}" | tr '[:upper:]' '[:lower:]')
  host_arg=$opt_host
  if [ ${#positional[@]} -eq 2 ]; then
    [ "$cmd" = find ] && usage_error "find takes no address; use --host <address> to test one address."
    host_arg=$(normalize_host "${positional[1]}") || usage_error "Not a valid robot name or address: ${positional[1]}"
  fi
  case $cmd in
    find) do_find "$host_arg"; exit $? ;;
    connect) require_ssh || exit 2; do_connect "$host_arg" 0; exit $? ;;
    status) require_ssh || exit 2; do_status "$host_arg" 0; exit $? ;;
    stop) require_ssh || exit 2; do_stop "$host_arg" 0; exit $? ;;
    setup-key) require_ssh || exit 2; do_setup_key "$host_arg" 0; exit $? ;;
    *) usage_error "Unknown command: ${positional[0]}" ;;
  esac
}

main "$@"
