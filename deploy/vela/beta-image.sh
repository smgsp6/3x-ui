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
    local actor
    actor=$(gh api user --jq .login)
    export DOCKER_CONFIG
    DOCKER_CONFIG=$(mktemp -d)
    trap 'rm -rf -- "$DOCKER_CONFIG"' EXIT
    printf '%s' "$GH_TOKEN" | docker login ghcr.io --username "$actor" --password-stdin >/dev/null
}

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)

check_delivery() {
    [[ "${APPROVED_DELIVERY_SHA:-}" =~ ^[0-9a-f]{40}$ ]] || fail 'Approved delivery commit is required.'
    local root
    root=$(git -C "$script_dir" rev-parse --show-toplevel)
    test "$(git -C "$root" rev-parse HEAD)" = "$APPROVED_DELIVERY_SHA"
    test -z "$(git -C "$root" status --porcelain --untracked-files=all)"
}

lock_docker() {
    [[ "${VELA_EXCLUSIVE_DOCKER:-}" == YES ]] || fail 'Owner-approved exclusive Docker daemon is required.'
    [[ -z "${DOCKER_HOST:-}" && -z "${DOCKER_CONTEXT:-}" && -z "${BUILDX_BUILDER:-}" ]] ||
        fail 'Remote Docker or builder overrides are forbidden.'
    [[ "$(docker context show)" == default ]] || fail 'Default local Docker context is required.'
    [[ "$(docker context inspect default --format '{{.Endpoints.docker.Host}}')" == unix:///var/run/docker.sock ]] ||
        fail 'Local Docker socket is required.'
    : "${XDG_RUNTIME_DIR:?A private runtime directory is required}"
    [[ -d "$XDG_RUNTIME_DIR" && ! -L "$XDG_RUNTIME_DIR" &&
       "$(stat -c '%u:%a' "$XDG_RUNTIME_DIR")" == "$(id -u):700" ]] || fail 'Unsafe runtime directory.'
    exec 9>"$XDG_RUNTIME_DIR/vela-beta-delivery.lock"
    flock -n 9 || fail 'Another beta delivery is active.'
}

token_scopes() {
    : "${GH_TOKEN:?An approved token is required}"
    gh api -i user | sed -n 's/^[Xx]-[Oo][Aa]uth-[Ss]copes:[[:space:]]*//p' | tr -d '[:space:]'
}

check_publisher() {
    [[ -n "${APPROVED_PUBLISHER:-}" ]] || fail 'The owner-approved publisher login is required.'
    local actor
    actor=$(gh api user --jq .login)
    [[ "$actor" == "$APPROVED_PUBLISHER" ]] || fail 'Authenticated publisher does not match approval.'
    local scopes
    scopes=$(token_scopes)
    [[ "$scopes" == write:packages || "$scopes" == write:packages,read:packages ||
       "$scopes" == read:packages,write:packages ]] ||
        fail 'Publisher must use a package-only token (no repo, delete, or admin scopes).'
}

case "${1:-}" in
    precheck)
        precheck
        ;;
    build)
        unset GH_TOKEN GITHUB_TOKEN
        check_delivery
        lock_docker
        : "${VELA_INPUT_LOCK:?}" "${VELA_INPUT_DIR:?}" "${APPROVED_INPUT_LOCK_SHA256:?}"
        : "${VELA_BUILD_EVIDENCE:?}"
        evidence="$XDG_RUNTIME_DIR/vela-beta-evidence"
        [[ "$VELA_BUILD_EVIDENCE" == "$evidence" ]] || fail 'Use the dedicated evidence file in XDG_RUNTIME_DIR.'
        rm -f -- "$evidence"
        existing_containers=$(docker ps -aq)
        [[ -z "$existing_containers" ]] || fail 'Use a disposable Docker daemon with no existing containers.'
        for test_tag in vela-ci-recovery-old:local vela-ci-recovery-failed:local; do
            if docker image inspect "$test_tag" >/dev/null 2>&1; then fail 'Recovery test tag already exists.'; fi
        done
        test "$(git rev-parse HEAD)" = "$source_sha"
        test -z "$(git status --porcelain --untracked-files=all)"
        test "$(git branch --show-current)" = vela-dev
        python3 vela-development/integration/baseline_privacy_gate.py
        scratch=$(mktemp -d)
        trap 'rm -rf -- "$scratch"' EXIT
        # Archive only committed files, including when a local checkout has ignored files.
        git archive "$source_sha" | tar -x -C "$scratch"
        python3 deploy/vela/ci_prepare_dockerfile.py Dockerfile "$scratch/VelaCandidateDockerfile"
        runtime=$(python3 "$script_dir/beta-inputs.py" "$VELA_INPUT_LOCK" "$APPROVED_INPUT_LOCK_SHA256" "$VELA_INPUT_DIR" "$scratch")
        docker build --pull --no-cache --platform linux/amd64 \
            --label "org.opencontainers.image.version=$APPROVED_INPUT_LOCK_SHA256" \
            --label "org.opencontainers.image.source=https://github.com/$repo" \
            --label "org.opencontainers.image.revision=$source_sha" \
            -f "$scratch/VelaCandidateDockerfile" --tag "$candidate" "$scratch"
        check_image "$candidate"
        config_id=$(docker image inspect --format '{{.Id}}' "$candidate")
        docker image save "$config_id" | python3 deploy/vela/image_layer_audit.py --stdin --diagnostic-counts
        (cd "$scratch/frontend" && npm audit --omit=dev --audit-level=high --registry=https://registry.npmjs.org)
        # Static Go inspection only needs the embed directory to exist.
        mkdir -p "$scratch/internal/web/dist"
        touch "$scratch/internal/web/dist/.audit-placeholder"
        (cd "$scratch" && GOPROXY=https://proxy.golang.org GOSUMDB=sum.golang.org GOTOOLCHAIN=local go run golang.org/x/vuln/cmd/govulncheck@v1.9.0 ./...)
        # A downloaded, owner-reviewed scanner and database are required.
        : "${APPROVED_TRIVY_SHA256:?}" "${TRIVY_CACHE_DIR:?}" "${APPROVED_TRIVY_DB_SHA256:?}"
        [[ "$APPROVED_TRIVY_SHA256" =~ ^[0-9a-f]{64}$ && "$APPROVED_TRIVY_DB_SHA256" =~ ^[0-9a-f]{64}$ ]]
        test "$(sha256sum "$(command -v trivy)" | cut -d' ' -f1)" = "$APPROVED_TRIVY_SHA256"
        test "$(sha256sum "$TRIVY_CACHE_DIR/db/trivy.db" | cut -d' ' -f1)" = "$APPROVED_TRIVY_DB_SHA256"
        trivy image --image-src docker --scanners vuln --skip-db-update --skip-java-db-update             --offline-scan --cache-dir "$TRIVY_CACHE_DIR" --severity HIGH,CRITICAL --exit-code 1 "$config_id"
        python3 "$script_dir/beta-runtime-tests.py" "$scratch" "$config_id" "$runtime"
        test "$(docker image inspect --format '{{.Id}}' "$candidate")" = "$config_id"
        jq -n --arg image_id "$config_id" --arg lock "$APPROVED_INPUT_LOCK_SHA256"             --arg tool "$APPROVED_DELIVERY_SHA" --arg src "$source_sha"             --arg daemon "$(docker info --format '{{.ID}}')"             '{config_id:$image_id, lock:$lock, tool:$tool, source:$src, daemon:$daemon}' > "$evidence"
        printf 'Local checks passed. Config ID: %s\n' "$config_id"
        ;;
    publish)
        [[ "${2:-}" == PUBLISH-PRIVATE-BETA ]] || fail 'Explicit publish acknowledgment required.'
        check_delivery
        lock_docker
        check_publisher
        precheck
        check_image "$candidate"
        # Re-audit the exact config ID, then check that the tag still refers to it.
        config_id=$(docker image inspect --format '{{.Id}}' "$candidate")
        : "${APPROVED_INPUT_LOCK_SHA256:?}" "${VELA_BUILD_EVIDENCE:?}"
        [[ "$VELA_BUILD_EVIDENCE" == "$XDG_RUNTIME_DIR/vela-beta-evidence" &&
           ! -L "$VELA_BUILD_EVIDENCE" &&
           "$(stat -c '%u:%a' "$VELA_BUILD_EVIDENCE")" == "$(id -u):600" ]] ||
            fail 'Completed build evidence is required.'
        jq -e --arg id "$config_id" --arg lock "$APPROVED_INPUT_LOCK_SHA256"             --arg tool "$APPROVED_DELIVERY_SHA" --arg src "$source_sha"             --arg daemon "$(docker info --format '{{.ID}}')"             '. == {config_id:$id,lock:$lock,tool:$tool,source:$src,daemon:$daemon} and ($daemon | length > 0)'             "$VELA_BUILD_EVIDENCE" >/dev/null
        reviewer_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
        docker image save "$candidate" | python3 "$reviewer_dir/image_layer_audit.py" --stdin --diagnostic-counts
        test "$(docker image inspect --format '{{.Id}}' "$candidate")" = "$config_id"
        registry_login
        check_private_package
        check_unused_tag
        test "$(docker image inspect --format '{{.Id}}' "$candidate")" = "$config_id"
        push_result=$(docker push "$candidate")
        pushed_digest=$(sed -nE 's/^vela-beta-'"$source_sha"': digest: (sha256:[0-9a-f]{64}) size: [0-9]+[[:space:]]*$/\1/p' <<<"$push_result")
        [[ "$pushed_digest" =~ ^sha256:[0-9a-f]{64}$ ]] ||
            fail 'Push digest unavailable. Do not deploy or blindly retry.'
        printf 'Published manifest digest (pending independent verification): %s\n' "$pushed_digest"
        if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
            printf 'config_id=%s\n' "$config_id" >> "$GITHUB_OUTPUT"
        else
            printf 'Audited local config ID for independent verification: %s\n' "$config_id"
            printf 'Publisher Docker daemon ID: %s\n' "$(docker info --format '{{.ID}}')"
        fi
        ;;
    verify)
        [[ "${EXPECTED_CONFIG_ID:-}" =~ ^sha256:[a-f0-9]{64}$ ]] || fail 'Expected audited config ID is required.'
        [[ "${EXPECTED_PUSH_DIGEST:-}" =~ ^sha256:[a-f0-9]{64}$ ]] || fail 'Recorded push manifest digest is required.'
        check_delivery
        lock_docker
        : "${PUBLISH_DOCKER_ID:?Supply the recorded publisher Docker daemon ID}"
        verify_daemon=$(docker info --format '{{.ID}}')
        [[ -n "$verify_daemon" && "$verify_daemon" != "$PUBLISH_DOCKER_ID" ]] ||
            fail 'A Docker daemon independent of the publisher is required.'
        [[ "$(token_scopes)" == read:packages ]] || fail 'Independent verification requires a read-only package token.'
        check_private_package
        registry_login
        digest=$(docker buildx imagetools inspect "$candidate" --format '{{json .Manifest}}' | jq -er '.digest // .Digest')
        [[ "$digest" =~ ^sha256:[a-f0-9]{64}$ ]] || fail 'GHCR did not return a manifest digest.'
        [[ "$digest" == "$EXPECTED_PUSH_DIGEST" ]] || fail 'Remote manifest differs from the recorded push digest.'
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
