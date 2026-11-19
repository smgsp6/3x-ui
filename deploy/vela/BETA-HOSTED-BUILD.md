# Hosted beta build preflight

The public repository may use the standard Ubuntu 24.04 x64 GitHub-hosted runner. The build is triggered only by a push to `vela-dev` changing `deploy/vela/beta-build-lock.json`. That trigger file is deliberately absent. Add it only after the full input inventory passes review and before requesting approval for the single push. The workflow checks the VM's own Docker socket, empty container list, passwordless sudo for synthetic recovery, required tools, at least two logical CPUs, 6,500,000 KiB of memory and at least 12 GiB of available disk. Real resource sufficiency still requires a run.

## Verified partial inventory

| Input | Official source | SHA-256 | Remaining review |
| --- | --- | --- | --- |
| Node 26.13.1 Alpine, linux/amd64 | `docker.io/library/node:26.13.1-alpine` | `a90bda2938f2b57112d94ee2e3722c5346efca76e4a034042b5223197567a16c` | Node and base OS component inventory and vulnerabilities |
| Go 1.27.4 Alpine, linux/amd64 | `docker.io/library/golang:1.27.4-alpine` | `ea30e25680a5470bac02b08bb0e0a735fb75bd0ab7d431b9b95ee0abef362586` | Go and base OS component inventory and vulnerabilities |
| Alpine 3.22.4, linux/amd64 | `docker.io/library/alpine:3.22.4` | `2039be0c5ec6ce8566809626a252c930216a92109c043f282504accb5ee3c0c6` | Base OS and signed APK inventory, licenses and vulnerabilities |
| Xray v26.11.9 | Official XTLS GitHub release `Xray-linux-64.zip.dgst` | `b651f7e1d9966ee2c1b1ee1bf8b52c72771824d3065dce96bbc8bcc19ed95f82` | Recorded official published checksum; verify archive bytes at staging time and record vulnerability review; upstream MPL-2.0 confirmed |
| MTG v1.16.1 | Official mhsanaei/mtg-multi release and fixed source's archive verifier | `c4a0ee4b6652530d93d9cfdb171492678dff1dbbed9d5702f6d72de8b132d167` | Upstream MIT license confirmed; record vulnerability review and verify fetched bytes |

The Docker base digests above are platform manifests. No base images or binary archives have been tested as a combined candidate.

## Verified release bytes and database snapshot

The following release assets were fetched from the tagged GitHub releases and matched their upstream SHA-256 files. The leftmost name is the destination in the Vela build.

| Destination | Upstream release and file | SHA-256 |
| --- | --- | --- |
| `geoip.dat` | [Loyalsoldier 202611182204](https://github.com/Loyalsoldier/v2ray-rules-dat/releases/tag/202611182204), `geoip.dat` | `304ac8a1cbcc8166e4f5a4f32955e4d0fb77a1bd713583e371b30ee27f3659d8` |
| `geosite.dat` | Same release, `geosite.dat` | `268f30619cfe5db5a925766bf966045f23b58b9a57bbc00c00396eb548011814` |
| `geoip_IR.dat` | [chocolate4u 202611191350](https://github.com/chocolate4u/Iran-v2ray-rules/releases/tag/202611191350), `geoip.dat` | `d8b3c0404eb9eca79ee7bc9913c9e0ef194590f1c66e869480fca9eb5800f322` |
| `geosite_IR.dat` | Same release, `geosite.dat` | `7b956bd27d67615624274ee8d442a952486b8c8e789863fa7e3cf9bf7375116a` |
| `geoip_RU.dat` | [runetfreedom 202611191200](https://github.com/runetfreedom/russia-v2ray-rules-dat/releases/tag/202611191200), `geoip.dat` | `c8f8a74c3e02f8953d89d0b894fa3a238b341417e0583c2eecdb9bbf8026e717` |
| `geosite_RU.dat` | Same release, `geosite.dat` | `9ca41e1216ce16ade7ac83cf19b2154fd0752333f7b6e1d01ecb82d7a37d45ba` |

The geo projects' upstream repositories declare GPL version 3. Review the licenses and attribution requirements of the datasets included in the generated files before distribution.

[Trivy v0.72.0](https://github.com/aquasecurity/trivy/releases/tag/v0.72.0) Linux x86-64 archive matched the upstream checksum `bbb64b9695866ce4a7a8f5c9592002c5961cab378577fa3f8a040df362b9b2ea`. The archived executable hashed to `0e69edd134a3c338baa1a6806920773615d682b18cbc6a0cba2a3b658ef9b63e`. The tagged source declares Apache-2.0. The executable was inspected by hash and was not run. Upstream lists fixes by v0.72.0 for [GHSA-mcj4-mphf-j9ff](https://github.com/aquasecurity/trivy/security/advisories/GHSA-mcj4-mphf-j9ff), [GHSA-8rc5-4fr6-64pw](https://github.com/aquasecurity/trivy/security/advisories/GHSA-8rc5-4fr6-64pw) and [GHSA-q3fv-x8vg-qqm4](https://github.com/aquasecurity/trivy/security/advisories/GHSA-q3fv-x8vg-qqm4). The earlier v0.69.3 candidate falls in all three affected ranges.

The anonymous read-only GHCR request for `aquasecurity/trivy-db` returned a schema 2 snapshot updated at `2026-11-19T13:02:29Z`, with next update due at `2026-11-20T13:02:29Z`. Manifest bytes matched the registry digest and the downloaded layer matched its descriptor. Reverify freshness when finalizing the build lock.

| GHCR object | SHA-256 |
| --- | --- |
| Manifest | `3d43a23675cdf60cc598244cbc34f1ca4d66bb41827fea15ffe3c573139c6fdb` |
| Compressed layer | `b5c4d3e45df32dd93a1b7259baeb8bb56928b408d9135a67d63ddad4c5a7da23` |
| `trivy.db` | `923c9ac4d894e62da8020926c64e7bbff80f2562944708ac6804388eb1debec9` |
| `metadata.json` | `80b4809400c6d27b6ca101edd96792d411fc53c35be5e6c9c0068bdb3d678bd5` |

## Remaining release inputs

The current outbound proxy refused CONNECT with HTTP 403 for the official Alpine package website, security database, primary CDN and alternate dl-3, dl-4 and dl-5 domains. Obtain signed APKs and indexes through an authorized read-only route to Alpine's official repositories. Resolve both closures against their pinned base images. Builder roots are `build-base gcc curl unzip`. Runtime roots are `ca-certificates tzdata fail2ban bash curl openssl`. Verify package signatures using trusted Alpine keys, record exact versions and hashes, prove installation with networking disabled and review their licenses and Alpine security advisories. Complete component and advisory reviews for the base images, application dependencies, build-time tools and binary dependencies before adding the trigger lock. An official checksum establishes file integrity; license, transitive dependency and vulnerability review remain separate checks.

## Review the trigger input

Top-level JSON keys are `bases`, `files`, `trivy` and `db`. Every item carries `version`, `license` and `known_vulnerabilities` completed by the reviewer. These are review records. Actual dependency, image and runtime scans still run as separate gates.

- `bases` has `frontend`, `builder`, `runtime`, each with a digest-qualified official `ref`.
- `files` keys match `beta-inputs.py` asset names and the complete `builder/*.apk` and `runtime/*.apk` closures. Each has a versioned public upstream `url` and `sha256`.
- `trivy` has release `url`, `archive_sha256` and `binary_sha256`.
- `db` has `manifest_sha256`, `archive_sha256`, `database_sha256` and `metadata_sha256`, calculated from the public official OCI database and exact archived members.

The hosted job performs dependencies and image scanning, isolated HTTPS/auth, Xray TCP/UDP and real recovery against the same candidate. The job binds the source lock to the triggering Git commit, records staged digests in step outputs and rechecks the inputs before the delivery tool uses them. The VM retains private failure diagnostics only until teardown. The test image is discarded with the VM. Logs show the successful build's source, delivery, lock and config ID; no image or archive is pushed or uploaded. A later approved private publication will need its own audited artifact and independent pull verification.

## One-run Alpine evidence collection

The optional `vela-beta-apk-evidence.yml` job is independent of the build lock. It triggers on a push that changes its own workflow file on `vela-dev`. After approval, push that workflow once and review the public job log. The job pulls the fixed amd64 builder and runtime images, uses their trusted APK keys for repository updates and package verification, records package URLs, hashes, key fingerprints and installed package metadata, and proves offline installation in fresh containers with the network disabled. It uses no checkout action, secrets, sudo, publishing credentials, or artifact upload. The temporary VM discards the APK bytes. Use the resulting public evidence to review the component versions and security advisories before finalizing the lock. The final build will re-fetch and check those exact inputs.
