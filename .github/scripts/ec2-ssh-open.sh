#!/usr/bin/env bash
# Open (or reuse) the SSH control connection to the EC2 host. Traffic is
# tunnelled through SSM, and the key is authorised for 60 seconds by EC2
# Instance Connect, so no inbound port or stored SSH key is needed.
set -euo pipefail

if ssh -O check transpire 2>/dev/null; then
  exit 0
fi

aws ec2-instance-connect send-ssh-public-key \
  --instance-id "$EC2_INSTANCE_ID" \
  --instance-os-user ubuntu \
  --ssh-public-key "file://$HOME/.ssh/ec2_ephemeral.pub" >/dev/null

ssh -fN transpire
