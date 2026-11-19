# Hosted beta build preflight

The public repository may use the standard Ubuntu 24.04 x64 GitHub-hosted runner. The build is triggered only by a push to `vela-dev` changing `deploy/vela/beta-build-lock.json`. That trigger file is deliberately absent. Add it only after the full input inventory passes review and the owner approves the single push. The workflow checks the VM's own Docker socket, empty container list, passwordless sudo for synthetic recovery, required tools, 6,500,000 KiB of memory and at least 12 GiB of available disk. Real resource sufficiency still requires a run.

## Verified partial inventory

| Input | Official source | SHA-256 | Remaining review |
| --- | --- | --- | --- |
| Node 26.13.1 Alpine, linux/amd64 | `docker.io/library/node:26.13.1-alpine` | `a90bda2938f2b57112d94ee2e3722c5346efca76e4a034042b5223197567a16c` | Node and base OS component inventory and vulnerabilities |
| Go 1.27.4 Alpine, linux/amd64 | `docker.io/library/golang:1.27.4-alpine` | `ea30e25680a5470bac02b08bb0e0a735fb75bd0ab7d431b9b95ee0abef362586` | Go and base OS component inventory and vulnerabilities |
| Alpine 3.22.4, linux/amd64 | `docker.io/library/alpine:3.22.4` | `2039be0c5ec6ce8566809626a252c930216a92109c043f282504accb5ee3c0c6` | Base OS and signed APK inventory, licenses and vulnerabilities |
| Xray v26.11.9 | Official XTLS GitHub release `Xray-linux-64.zip.dgst` | `b651f7e1d9966ee2c1b1ee1bf8b52c72771824d3065dce96bbc8bcc19ed95f82` | Recorded official published checksum; verify archive bytes at staging time and record vulnerability review; upstream MPL-2.0 confirmed |
| MTG v1.16.1 | Official mhsanaei/mtg-multi release and fixed source's archive verifier | `c4a0ee4b6652530d93d9cfdb171492678dff1dbbed9d5702f6d72de8b132d167` | Upstream MIT license confirmed; record vulnerability review and verify fetched bytes |

The Docker base digests above are registry-resolved platform manifests. No base images or binary archives have been tested as a combined candidate. Alpine APK index and routing release API requests returned HTTP 403 in this environment. The signed builder/runtime APK closures, six geo files and license/vulnerability reviews, Trivy binary and official DB manifest/layer/member checksums are still missing.

## Review the trigger input

Top-level JSON keys are `bases`, `files`, `trivy` and `db`. Every item carries `version`, `license` and `known_vulnerabilities` completed by the reviewer. These are review records. Actual dependency, image and runtime scans still run as separate gates.

- `bases` has `frontend`, `builder`, `runtime`, each with a digest-qualified official `ref`.
- `files` keys match `beta-inputs.py` asset names and the complete `builder/*.apk` and `runtime/*.apk` closures. Each has a versioned public upstream `url` and `sha256`.
- `trivy` has release `url`, `archive_sha256` and `binary_sha256`.
- `db` has `manifest_sha256`, `archive_sha256`, `database_sha256` and `metadata_sha256`, calculated from the public official OCI database and exact archived members.

The hosted job performs dependencies and image scanning, isolated HTTPS/auth, Xray TCP/UDP and real recovery against the same candidate. The VM retains private failure diagnostics only until teardown. Logs show the successful build's source, delivery, lock and config ID; no image or archive is pushed or uploaded. A later approved private publication will need its own audited artifact and independent pull verification.
