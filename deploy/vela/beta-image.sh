#!/usr/bin/env bash
# Fixed-source private beta delivery. Run only on an approved local Docker daemon.
set -euo pipefail
umask 077

readonly source_sha=9ef190a504221c95925b5224005355bd1313c147
readonly repo=smgsp6/3x-ui
readonly image="ghcr.io/$repo"
readonly candidate="$image:vela-beta-$source_sha"
readonly package_api=users/smgsp6/packages/container/3x-ui
readonly ci_run="repos/$repo/actions/runs/44491849398"

fail() { printf '%s\n' "$1" >&2; exit 1; }

check_private_package() {
    gh api "$package_api" --jq .visibility | grep -qx private ||
        fail 'Existing private GHCR package required. Refusing to create or change package visibility.'
}

check_unused_tag() {
    versions=$(gh api --paginate "$package_api/versions" --jq '.[].metadata.container.tags[]?')
    if grep -Fxq "vela-beta-$source_sha" <<<"$versions"; then
        fail 'Candidate tag already exists. Do not overwrite it.'
    fi
}

precheck() {
    gh api "$ci_run" | jq -e --arg sha "$source_sha" '
        .head_sha == $sha and .head_branch == "vela-dev" and
        .path == ".github/workflows/vela-pr-check.yml" and .conclusion == "success"
    ' >/dev/null
    gh api "$ci_run/jobs?per_page=100" | jq -e '
        .total_count == 4 and (.jobs | length == 4 and all(.conclusion == "success"))
    ' >/dev/null
    check_private_package
    check_unused_tag
}

check_image() {
    local ref=$1
    test "$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$ref")" = linux/amd64
    test "$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$ref")" = "$source_sha"
    test "$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.source"}}' "$ref")" = "https://github.com/$repo"
}

registry_login() {
    : "${GH_TOKEN:?Supply an approved scoped token through the local environment}"
    local actor=${GITHUB_ACTOR:-}
    if [[ -z "$actor" ]]; then
        actor=$(gh api user --jq .login)
    fi
    export DOCKER_CONFIG
    DOCKER_CONFIG=$(mktemp -d)
    trap 'rm -rf -- "$DOCKER_CONFIG"' EXIT
    printf '%s' "$GH_TOKEN" | docker login ghcr.io --username "$actor" --password-stdin >/dev/null
}

case "${1:-}" in
    precheck)
        precheck
        ;;
    build)
        unset GH_TOKEN GITHUB_TOKEN
        test "$(git rev-parse HEAD)" = "$source_sha"
        test -z "$(git status --porcelain --untracked-files=all)"
        test "$(git branch --show-current)" = vela-dev
        python3 vela-development/integration/baseline_privacy_gate.py
        scratch=$(mktemp -d)
        trap 'rm -rf -- "$scratch"' EXIT
        # Archive only committed files, including when a local checkout has ignored files.
        git archive "$source_sha" | tar -x -C "$scratch"
        python3 deploy/vela/ci_prepare_dockerfile.py Dockerfile "$scratch/VelaCandidateDockerfile"
        docker build --pull --no-cache --platform linux/amd64 \
            --label "org.opencontainers.image.source=https://github.com/$repo" \
            --label "org.opencontainers.image.revision=$source_sha" \
            -f "$scratch/VelaCandidateDockerfile" --tag "$candidate" "$scratch"
        check_image "$candidate"
        docker image save "$candidate" | python3 deploy/vela/image_layer_audit.py --stdin --diagnostic-counts
        ;;
    publish)
        [[ "${2:-}" == PUBLISH-PRIVATE-BETA ]] || fail 'Explicit publish acknowledgment required.'
        precheck
        check_image "$candidate"
        # Re-audit the exact config ID, then check that the tag still refers to it.
        config_id=$(docker image inspect --format '{{.Id}}' "$candidate")
        reviewer_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
        docker image save "$candidate" | python3 "$reviewer_dir/image_layer_audit.py" --stdin --diagnostic-counts
        test "$(docker image inspect --format '{{.Id}}' "$candidate")" = "$config_id"
        registry_login
        check_private_package
        check_unused_tag
        docker push "$candidate"
        if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
            printf 'config_id=%s\n' "$config_id" >> "$GITHUB_OUTPUT"
        else
            printf 'Audited local config ID for independent verification: %s\n' "$config_id"
        fi
        ;;
    verify)
        [[ "${EXPECTED_CONFIG_ID:-}" =~ ^sha256:[a-f0-9]{64}$ ]] || fail 'Expected audited config ID is required.'
        check_private_package
        registry_login
        digest=$(docker buildx imagetools inspect "$candidate" --format '{{json .Manifest}}' | jq -er '.digest // .Digest')
        [[ "$digest" =~ ^sha256:[a-f0-9]{64}$ ]] || fail 'GHCR did not return a manifest digest.'
        docker pull --platform linux/amd64 "$image@$digest"
        check_image "$image@$digest"
        test "$(docker image inspect --format '{{.Id}}' "$image@$digest")" = "$EXPECTED_CONFIG_ID"
        check_private_package
        printf 'Verified pull reference: %s@%s\n' "$image" "$digest"
        if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
            printf 'Verified pull reference: `%s@%s`\n' "$image" "$digest" >> "$GITHUB_STEP_SUMMARY"
        fi
        ;;
    *) fail 'Usage: bash beta-image.sh precheck|build|publish|verify' ;;
esac
