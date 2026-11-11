#!/bin/bash
# repo is source of truth -> live Hermes skill dir
rsync -a --delete /root/opencode-stuffs/Frontier-UI/hermes-port/skill/ /root/.hermes/skills/generative-ui-widgets/
echo synced.
