"""Run the fixed revision's isolated Docker contracts against the audited image."""
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml


def main():
    context = Path(sys.argv[1]).resolve()
    image_id, runtime = sys.argv[2:]
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise ValueError("expected audited config ID")
    if not re.fullmatch(r"docker.io/library/alpine@sha256:[0-9a-f]{64}", runtime):
        raise ValueError("expected approved test base")
    workflow = yaml.load((context / ".github/workflows/vela-pr-check.yml").read_text(),
                         Loader=yaml.BaseLoader)
    steps = {step["name"]: step["run"] for step in workflow["jobs"]["docker"]["steps"]
             if "name" in step and "run" in step}
    env = {**os.environ, "RUNNER_TEMP": str(context)}
    for key in ("GH_TOKEN", "GITHUB_TOKEN"):
        env.pop(key, None)

    def run(name, source, target):
        body = steps[name].replace(source, target)
        subprocess.run(["bash", "-euo", "pipefail", "-c", body], check=True, cwd=context, env=env)

    try:
        run("Prepare ephemeral signed HTTPS certificate and synthetic Bot Token",
            "vela-integration-ci:local", image_id)
        run("Verify genuine HTTPS auth, Xray and live certificate rotation",
            "vela-integration-ci:local", image_id)
    finally:
        run("Delete transient local credentials and certificates", "\0", "")
    subprocess.run(["docker", "tag", image_id, "vela-ci-recovery-old:local"], check=True, env=env)
    try:
        run("Build deliberately unhealthy synthetic candidate", "FROM alpine:3.22", f"FROM {runtime}")
        recovery = context / "tests/ci_real_docker_recover.py"
        source = recovery.read_text()
        guard = 'os.environ.get("GITHUB_ACTIONS") == "true"'
        if source.count(guard) != 1:
            raise ValueError("unexpected recovery harness guard")
        recovery.write_text(source.replace(guard, 'os.environ.get("VELA_EXCLUSIVE_DOCKER") == "YES"'))
        subprocess.run(["sudo", "env", "VELA_EXCLUSIVE_DOCKER=YES", f"PATH={os.environ['PATH']}",
                        "python3", str(recovery)], check=True, cwd=context, env=env)
    finally:
        subprocess.run(["docker", "image", "rm", "vela-ci-recovery-old:local",
                        "vela-ci-recovery-failed:local"], env=env, check=False)


if __name__ == "__main__":
    main()
