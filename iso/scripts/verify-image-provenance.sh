#!/usr/bin/env bash
# Verify the new Utah image's SLSA provenance attestation before it is pulled
# and used as privileged e2e media (utah#1018). Digest-locking the pin stops an
# accidental tag move; this stops an unsigned image -- or one attested by any
# other workflow or repo -- from running the privileged ISO build and install
# tests. post-testing-e2e calls it on the exact ref the luks and tacklebox jobs
# are about to pull, so the check and the privileged use share the same pin.
set -euo pipefail

# build.yml publishes the attestation keylessly on testing; pin its Fulcio
# identity so an attestation from any other workflow, branch, or repository is
# rejected. Only the testing branch is accepted, anchored, so no other ref can
# match.
readonly ATTEST_IDENTITY_REGEXP='^https://github\.com/projectbluefin/utah/\.github/workflows/build\.yml@refs/heads/testing$'

# The ref is a digest from the exact build being validated (resolve-e2e-inputs),
# so no config file: the pin and the pull are the same string.
IMAGE="${1:-}"
[[ -n "$IMAGE" ]] || { echo "ERROR: usage: verify-image-provenance.sh <digest-pinned image-ref>" >&2; exit 2; }
[[ "$IMAGE" =~ ^[^[:space:]@]+@sha256:[a-f0-9]{64}$ ]] || {
    echo "ERROR: image must be digest-pinned: ${IMAGE}" >&2
    exit 2
}

# cosign is in neither the base image nor the runner's default apt list, so
# install the version-pinned binary and confirm its SHA before trusting it to
# verify the image that is about to run privileged.
command -v cosign >/dev/null 2>&1 || {
    echo "==> Installing cosign v3.1.4 to verify the attestation..."
    case "$(uname -m)" in
        x86_64) asset=cosign-linux-amd64; sha=424e2c97d0b45fd7a6b608a87f090f35633f4c23ece5f092d48bba11aaf4bbfa ;;
        aarch64) asset=cosign-linux-arm64; sha=ade83b7aac62e131cacfe96d958948b2150cc9efec46a570a2649b8e27dedad2 ;;
        *) echo "ERROR: $(uname -m) is not supported; install cosign manually." >&2; exit 1 ;;
    esac
    # Download outside any bin path and install only once the checksum
    # passes, so a mismatch never leaves an unverified binary on PATH.
    tmp=$(mktemp)
    trap 'rm -f "$tmp"' EXIT
    curl -fsSL --retry 3 --retry-delay 5 -o "$tmp" \
        "https://github.com/sigstore/cosign/releases/download/v3.1.4/${asset}"
    echo "${sha}  ${tmp}" | sha256sum --check --status
    install -m 0755 "$tmp" /usr/local/bin/cosign
}

# Pull with the workflow token first: cosign reads ~/.docker/config.json for
# registry auth, and ghcr needs it even for a public org. podman login seeds that
# file so the attestation fetch below can reach the registry.
echo "==> Logging in to ghcr.io for the attestation fetch"
echo "${GH_TOKEN}" | podman login ghcr.io -u "$GITHUB_ACTOR" --password-stdin

echo "==> Verifying SLSA provenance of ${IMAGE} (utah#1018)"
cosign verify-attestation \
    --type=https://slsa.dev/provenance/v1 \
    --certificate-oidc-issuer="https://token.actions.githubusercontent.com" \
    --certificate-identity-regexp="${ATTEST_IDENTITY_REGEXP}" \
    "${IMAGE}"
