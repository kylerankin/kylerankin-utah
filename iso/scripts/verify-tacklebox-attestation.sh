#!/usr/bin/env bash
# Verify the published tuna-os/tacklebox builder image's SLSA provenance
# attestation before it is run with --privileged (utah#918). Digest-locking the
# pin stops an accidental tag move; this stops an unsigned image -- or one
# attested by any other workflow or repo -- from running as root with /dev
# mounted. The build script and post-testing-e2e both call it, so the check and
# the privileged run can never disagree on which image is trusted.
set -euo pipefail

# Single source of truth for the tacklebox pin. Read it back from here by the
# build script and the workflow so the digest cannot drift between the
# attestation check and the pull. Override with TACKLEBOX_IMAGE to test a new
# image locally.
readonly DEFAULT_TACKLEBOX_IMAGE="ghcr.io/tuna-os/tacklebox:latest@sha256:7415c1c23f83918b0c22f14ceee199e46f47e8411f54582d8b8899837c2c3441"
# release-image.yml publishes the attestation keylessly; pin its Fulcio identity
# so an attestation from any other workflow or repository is rejected.
readonly ATTEST_IDENTITY="https://github.com/tuna-os/tacklebox/.github/workflows/release-image.yml@refs/heads/main"

# Echo the pin without installing cosign or touching a registry, so callers can
# read the same digest the build uses (utah#918).
if [[ "${1:-}" == "--print-image" ]]; then
    printf '%s\n' "${TACKLEBOX_IMAGE:-$DEFAULT_TACKLEBOX_IMAGE}"
    exit 0
fi

IMAGE="${TACKLEBOX_IMAGE:-$DEFAULT_TACKLEBOX_IMAGE}"

# cosign is in neither the base image nor the runner's default apt list, so
# install the version-pinned binary and confirm its SHA before trusting it to
# verify the image that is about to run as root.
command -v cosign >/dev/null 2>&1 || {
    echo "==> Installing cosign v3.1.4 to verify the tacklebox attestation..."
    case "$(uname -m)" in
        x86_64) asset=cosign-linux-amd64; sha=424e2c97d0b45fd7a6b608a87f090f35633f4c23ece5f092d48bba11aaf4bbfa ;;
        aarch64) asset=cosign-linux-arm64; sha=ade83b7aac62e131cacfe96d958948b2150cc9efec46a570a2649b8e27dedad2 ;;
        *) echo "ERROR: $(uname -m) is not supported; install cosign manually." >&2; exit 1 ;;
    esac
    curl -fsSL -o /usr/local/bin/cosign \
        "https://github.com/sigstore/cosign/releases/download/v3.1.4/${asset}"
    echo "${sha}  /usr/local/bin/cosign" | sha256sum --check --status
    chmod +x /usr/local/bin/cosign
}

echo "==> Verifying SLSA provenance of ${IMAGE} (utah#918)"
cosign verify-attestation \
    --type=https://slsa.dev/provenance/v1 \
    --certificate-oidc-issuer="https://token.actions.githubusercontent.com" \
    --certificate-identity="${ATTEST_IDENTITY}" \
    "${IMAGE}"
