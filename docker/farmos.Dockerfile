# Production farmOS image: a pinned base with the farm_syntropic module baked in.
#
# The dev stacks (docker-compose.development.yml + the smoke test) track the
# MOVING `farmos/farmos:4.x-dev` tag and bind-mount the module live. Production
# must be reproducible and self-contained instead, so here we:
#   1. pin the farmOS base by DIGEST (not a floating tag), and
#   2. COPY the module into the image (no bind-mount).
#
# The digest is the ONE place the farmOS version advances in prod — bump it
# deliberately. To resolve the current digest of the 4.x-dev tag:
#   docker buildx imagetools inspect farmos/farmos:4.x-dev
# (or query the registry manifest for `farmos/farmos:4.x-dev`).
#
# Digest below resolved on 2026-06-16. Build context must be the REPO ROOT so
# the COPY can see modules/ (see docker-compose.prod.yml: context `..`).
ARG FARMOS_DIGEST=sha256:5d8f5cc4183465a80037b45eae58bdd420fc4757ac9918bb6c7bcdf825c8731d
FROM farmos/farmos@${FARMOS_DIGEST}

# Bake the custom module in. In dev this path is a bind-mount; in prod it is
# image content, so a deploy ships exactly the module committed to the repo.
COPY modules/farm_syntropic /opt/drupal/web/modules/farm_syntropic

# Xdebug cripples request latency even when idle — it must be off in prod.
ENV XDEBUG_MODE=off
