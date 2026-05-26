#!/usr/bin/env bash
# Manual operator steps requiring sudo — from prop_20260526_004 implementation.
# Run as: sudo bash ops_manual_steps.sh
# Safe to run multiple times (idempotent).
set -euo pipefail

echo "=== P1b: Remove defunct btc-alt-watchlist unit files ==="
# Timer was already disabled/masked. Remove the unit files entirely
# so a future daemon-reload can't accidentally re-enable them.
rm -f /etc/systemd/system/btc-alt-watchlist.timer
rm -f /etc/systemd/system/btc-alt-watchlist.service
echo "  Removed btc-alt-watchlist.{timer,service}"


echo ""
echo "=== P2e: Add Restart=on-failure to high-frequency collectors ==="
# btc-candles.service
if ! grep -q 'Restart=on-failure' /etc/systemd/system/btc-candles.service; then
  sed -i '/^\[Service\]/a Restart=on-failure\nRestartSec=60' /etc/systemd/system/btc-candles.service
  echo "  Patched btc-candles.service"
else
  echo "  btc-candles.service already has Restart=on-failure"
fi

# btc-news.service
if ! grep -q 'Restart=on-failure' /etc/systemd/system/btc-news.service; then
  sed -i '/^\[Service\]/a Restart=on-failure\nRestartSec=60' /etc/systemd/system/btc-news.service
  echo "  Patched btc-news.service"
else
  echo "  btc-news.service already has Restart=on-failure"
fi

# btc-derivatives.service
if ! grep -q 'Restart=on-failure' /etc/systemd/system/btc-derivatives.service; then
  sed -i '/^\[Service\]/a Restart=on-failure\nRestartSec=60' /etc/systemd/system/btc-derivatives.service
  echo "  Patched btc-derivatives.service"
else
  echo "  btc-derivatives.service already has Restart=on-failure"
fi


echo ""
echo "=== P2e: Install btc-collector-notify@.service (OnFailure sidecar) ==="
cat > /etc/systemd/system/btc-collector-notify@.service << 'EOF'
[Unit]
Description=Collector failure notifier for %i
[Service]
Type=oneshot
User=btc-agent
ExecStart=/bin/bash -c \
  'echo "{\"collector\":\"%i\",\"failed_at\":\"$(date -u +%%Y-%%m-%%dT%%H:%%M:%%SZ)\"}" \
  >> /home/btc-agent/btc-agents/data/meta/collector_failures.json'
EOF
echo "  Written btc-collector-notify@.service"

# Wire OnFailure into the three high-frequency services
for svc in btc-candles btc-news btc-derivatives; do
  if ! grep -q 'OnFailure' /etc/systemd/system/${svc}.service; then
    sed -i '/^\[Unit\]/a OnFailure=btc-collector-notify@%i.service' /etc/systemd/system/${svc}.service
    echo "  Added OnFailure to ${svc}.service"
  else
    echo "  ${svc}.service already has OnFailure"
  fi
done


echo ""
echo "=== Reloading systemd ==="
systemctl daemon-reload
echo "  daemon-reload done"

echo ""
echo "=== Restarting btc-collection-monitor (picks up collection_monitor.py changes) ==="
systemctl restart btc-collection-monitor.service
sleep 2
systemctl is-active btc-collection-monitor.service && echo "  btc-collection-monitor: active" || echo "  WARNING: btc-collection-monitor not active"

echo ""
echo "=== Verification ==="
echo "Active timers:"
systemctl list-timers 2>/dev/null | grep btc | grep -v alt-watchlist || true
echo ""
echo "btc-alt-watchlist.timer: $(systemctl is-enabled btc-alt-watchlist.timer 2>/dev/null || echo 'gone (good)')"
echo ""
echo "Done. All P1b + P2e steps complete."
