# VM tick

GitHub ran the `*/30` cron only ~3x/day, so the gridbot VM triggers `run.yml` every 30 min.

Install (token = fine-grained PAT: repo `marketing-engine` only, **Contents: read and write**, nothing else):

    sudo mkdir -p /etc/marketing-engine
    echo "GH_TOKEN=github_pat_..." | sudo tee /etc/marketing-engine/tick.env >/dev/null
    sudo chmod 600 /etc/marketing-engine/tick.env
    sudo cp me-tick.service me-tick.timer /etc/systemd/system/
    sudo systemctl daemon-reload && sudo systemctl enable --now me-tick.timer

Check: `systemctl list-timers me-tick.timer`, `journalctl -u me-tick -n 20`. The PAT expires; rotate it there.
