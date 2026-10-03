#!/bin/bash
SSID="Students"
AP="netplan-wlan0-Turtlebot4"
DIR=/home/ubuntu/wifi-switch
LOG="$DIR/log.txt"
HOLD=180
GO_WAIT=1800
KEEP_WAIT=600

log(){ echo "$(date '+%F %T') $*" >> "$LOG"; chown ubuntu:ubuntu "$LOG" 2>/dev/null; }
wlan_ip(){ ip -4 -o addr show dev wlan0 | awk '{print $4}' | cut -d/ -f1 | head -1; }
on_students(){ local ip; ip=$(wlan_ip); [ -n "$ip" ] && [ "${ip#10.42.}" = "$ip" ]; }

join(){
  log "Joining $SSID"
  nmcli device disconnect wlan0 >>"$LOG" 2>&1
  local n ip
  for n in 1 2 3; do
    sleep 3
    nmcli device wifi rescan ifname wlan0 ssid "$SSID" >/dev/null 2>&1
    sleep 8
    log "Seen: $(nmcli -t -f SSID,SIGNAL,FREQ device wifi list ifname wlan0 --rescan no | grep "^$SSID:" | head -3 | tr '\n' ' ')"
    if nmcli -w 45 connection up "$SSID" >>"$LOG" 2>&1; then break; fi
    log "Attempt $n to join $SSID failed"
    [ "$n" -eq 3 ] && return 1
  done
  for n in $(seq 1 30); do on_students && break; sleep 2; done
  if ! on_students; then log "Joined $SSID but got no address"; return 1; fi
  ip=$(wlan_ip); echo "$ip" > "$DIR/students_ip.txt"; chown ubuntu:ubuntu "$DIR/students_ip.txt"
  log "Address on $SSID: $ip"
}

checks(){
  local gw code
  gw=$(ip -4 route show default dev wlan0 | awk '{print $3}' | head -1); log "Gateway: ${gw:-none}"
  if [ -n "$gw" ] && ping -c2 -W2 "$gw" >/dev/null 2>&1; then log "Ping gateway: OK"; else log "Ping gateway: no reply"; fi
  if ping -c2 -W3 1.1.1.1 >/dev/null 2>&1; then log "Ping internet: OK"; else log "Ping internet: no reply"; fi
  if getent hosts packages.ros.org >/dev/null 2>&1; then log "DNS: OK"; else log "DNS: failed"; fi
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 http://connectivitycheck.gstatic.com/generate_204)
  log "Web check: HTTP ${code:-none} (204 = open internet, anything else suggests a login page)"
}

back_to_ap(){
  log "Going back to the robot's own Wi-Fi"
  nmcli -w 60 connection up "$AP" >>"$LOG" 2>&1 && return 0
  sleep 10; nmcli -w 60 connection up "$AP" >>"$LOG" 2>&1 && return 0
  log "nmcli could not restore the robot's own Wi-Fi, running netplan apply"
  netplan apply >>"$LOG" 2>&1
}

rm -f "$DIR/GO" "$DIR/KEEP"
log "=== Test phase ==="
sleep 10
if join; then checks; log "Staying on $SSID for $HOLD s so the laptop can try to reach the robot"; sleep "$HOLD"; else log "TEST FAILED"; fi
back_to_ap
log "TEST DONE. Waiting up to $GO_WAIT s for the go-ahead file $DIR/GO"
for i in $(seq 1 $((GO_WAIT/5))); do [ -f "$DIR/GO" ] && break; sleep 5; done
if [ ! -f "$DIR/GO" ]; then log "No go-ahead. Staying on the robot's own Wi-Fi. Finished."; exit 0; fi
rm -f "$DIR/GO"

log "=== Permanent phase ==="
if ! join; then back_to_ap; log "PERMANENT SWITCH FAILED. Back on the robot's own Wi-Fi."; exit 1; fi
checks
nmcli connection modify "$SSID" connection.autoconnect yes connection.autoconnect-priority 10 >>"$LOG" 2>&1
log "Waiting up to $KEEP_WAIT s for the confirmation file $DIR/KEEP, otherwise undoing"
for i in $(seq 1 $((KEEP_WAIT/5))); do [ -f "$DIR/KEEP" ] && break; sleep 5; done
if [ -f "$DIR/KEEP" ]; then
  log "CONFIRMED. The robot stays on $SSID. Its own Wi-Fi remains the fallback when $SSID is out of range."
  exit 0
fi
nmcli connection modify "$SSID" connection.autoconnect no >>"$LOG" 2>&1
back_to_ap
log "NOT CONFIRMED. Undone: back on the robot's own Wi-Fi, and $SSID will not auto-connect."
