from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_arc_runner_is_zero_idle_single_job_capacity_and_secret_refs_only():
    path = ROOT / "infra/private-certifier/arc-runner-values.yaml"
    text = path.read_text(encoding="utf-8")
    cfg = yaml.safe_load(text)
    assert cfg["runnerScaleSetName"] == "trading-certifier-jit"
    assert cfg["minRunners"] == 0
    assert cfg["maxRunners"] == 1
    assert cfg["githubConfigSecret"] == "trading-certifier-github-app"
    assert cfg["template"]["spec"]["automountServiceAccountToken"] is False
    assert "tskey-" not in text
    assert "BEGIN PRIVATE KEY" not in text
    assert "github_token:" not in text
    containers = {c["name"]: c for c in cfg["template"]["spec"]["containers"]}
    assert "runner" in containers and "tailscale" in containers
    ts_env = {e["name"]: e for e in containers["tailscale"]["env"]}
    assert ts_env["TS_USERSPACE"]["value"] == "true"
    assert "secretKeyRef" in ts_env["TS_AUTHKEY"]["valueFrom"]
    security = containers["tailscale"]["securityContext"]
    assert security["allowPrivilegeEscalation"] is False
    assert security["runAsNonRoot"] is True


def test_kubernetes_namespace_is_restricted_and_default_deny():
    docs = list(yaml.safe_load_all((ROOT / "infra/private-certifier/kubernetes-isolation.yaml").read_text()))
    namespace = docs[0]
    assert namespace["metadata"]["name"] == "arc-runners"
    assert namespace["metadata"]["labels"]["pod-security.kubernetes.io/enforce"] == "restricted"
    default_deny = docs[1]
    assert default_deny["kind"] == "NetworkPolicy"
    assert default_deny["spec"]["podSelector"] == {}
    assert set(default_deny["spec"]["policyTypes"]) == {"Ingress", "Egress"}


def test_runtime_workflow_is_manual_fail_closed_and_never_authorizes_trading():
    text = (ROOT / ".github/workflows/private-certifier-runtime.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "runs-on: trading-certifier-jit" in text
    assert 'test "$GITHUB_SHA" = "$EXPECTED_SHA"' in text
    assert 'test "${CI_RUNNER_EPHEMERAL:-}" = "true"' in text
    assert "socks5h://localhost:1055" in text
    assert "*.ts.net" in text
    for key in ("paper", "testnet", "shadow", "live_pilot", "live"):
        assert f'"{key}": False' in text
