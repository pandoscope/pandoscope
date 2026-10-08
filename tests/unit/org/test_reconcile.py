from __future__ import annotations

from pathlib import Path

import pytest

from pandoscope.org.confs import Credentials
from pandoscope.org.plan import Repo
from pandoscope.org.reconcile import Outcome, reconcile

PLAN = [
    Repo("meta", "m", {"agentic_subtemplate": "template"}),
    Repo("session-memory", "s", {"agentic_subtemplate": "x"}, direct_pushes=True),
]
CREDS = Credentials(app_slug="o-release-bot", client_id="Iv23x", board_url=None)


def fake_meta(root: Path) -> Path:
    scripts = root / "meta" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "repo-settings.conf").write_text(
        'ORG="pandoscope"\nSETTINGS=(\n    "has_wiki|false|all"\n)\n'
    )
    (scripts / "repo-rulesets.conf").write_text(
        'ORG="pandoscope"\nRULESETS=(\n    "p.json|except:session-memory,waybill"\n)\n'
    )
    (scripts / "repo-collaborators.conf").write_text('ORG="pandoscope"\n')
    for name in ("settings", "rulesets", "collaborators"):
        (scripts / f"sync-gh-repo-{name}.sh").write_text("#!/usr/bin/env bash\n")
    (scripts / "sync-gh-actions-credentials.sh").write_text("#!/usr/bin/env bash\n")
    return root / "meta"


class FakeExec:
    def __init__(self, codes: dict[str, int] | None = None, out: str = "") -> None:
        self.calls: list[tuple[list[str], dict[str, str]]] = []
        self.codes = codes or {}
        self.out = out

    def __call__(self, cmd: list[str], env: dict[str, str]) -> tuple[int, str]:
        self.calls.append((cmd, env))
        script = Path(cmd[1]).name
        return self.codes.get(script, 0), self.out

    def scripts(self) -> list[str]:
        return [
            Path(cmd[1]).name + "".join(" " + a for a in cmd[2:])
            for cmd, _ in self.calls
        ]


def test_scripts_run_in_dependency_order(tmp_path: Path) -> None:
    meta, secrets = fake_meta(tmp_path), tmp_path / "secrets"
    secrets.mkdir()
    fake = FakeExec()
    reconcile("o", PLAN, meta, secrets, CREDS, dry_run=False, exec_=fake)
    assert fake.scripts() == [
        "sync-gh-repo-settings.sh",
        "sync-gh-repo-rulesets.sh",
        "sync-gh-actions-credentials.sh",
        "sync-gh-repo-collaborators.sh",
    ]


def test_each_script_reads_its_generated_conf(tmp_path: Path) -> None:
    meta, secrets = fake_meta(tmp_path), tmp_path / "secrets"
    secrets.mkdir()
    fake = FakeExec()
    reconcile("o", PLAN, meta, secrets, CREDS, dry_run=False, exec_=fake)
    envs = [env for _, env in fake.calls]
    rulesets = Path(envs[1]["SYNC_RULESETS_CONF"]).read_text()
    assert 'ORG="o"' in rulesets
    assert '"p.json|except:session-memory"' in rulesets
    assert 'ORG="o"' in Path(envs[0]["SYNC_SETTINGS_CONF"]).read_text()
    assert 'ORG="o"' in Path(envs[3]["SYNC_COLLABORATORS_CONF"]).read_text()
    assert "o-release-bot" in Path(envs[2]["SYNC_CREDENTIALS_CONF"]).read_text()
    assert envs[2]["SYNC_CREDENTIALS_SECRETS_DIR"] == str(secrets)


def test_state_stays_under_the_orgs_secrets_dir(tmp_path: Path) -> None:
    meta, secrets = fake_meta(tmp_path), tmp_path / "secrets"
    secrets.mkdir()
    fake = FakeExec()
    reconcile("o", PLAN, meta, secrets, CREDS, dry_run=False, exec_=fake)
    envs = [env for _, env in fake.calls]
    for key in ("SYNC_SETTINGS_STATE_DIR",):
        assert envs[0][key].startswith(str(secrets))
    assert envs[1]["SYNC_RULESETS_STATE_DIR"].startswith(str(secrets))


def test_scripts_run_from_the_meta_checkout(tmp_path: Path) -> None:
    meta, secrets = fake_meta(tmp_path), tmp_path / "secrets"
    secrets.mkdir()
    fake = FakeExec()
    reconcile("o", PLAN, meta, secrets, CREDS, dry_run=False, exec_=fake)
    for cmd, _ in fake.calls:
        assert cmd[0] == "bash"
        assert Path(cmd[1]).parent == meta / "scripts"


def test_dry_run_passes_dry_run_to_every_script(tmp_path: Path) -> None:
    meta, secrets = fake_meta(tmp_path), tmp_path / "secrets"
    secrets.mkdir()
    fake = FakeExec()
    reconcile("o", PLAN, meta, secrets, CREDS, dry_run=True, exec_=fake)
    assert all(cmd[-1] == "--dry-run" for cmd, _ in fake.calls)


def test_a_fresh_secrets_dir_is_seeded_before_the_credentials_run(
    tmp_path: Path,
) -> None:
    meta, secrets = fake_meta(tmp_path), tmp_path / "secrets"
    fake = FakeExec()
    reconcile("o", PLAN, meta, secrets, CREDS, dry_run=False, exec_=fake)
    assert fake.scripts()[2:4] == [
        "sync-gh-actions-credentials.sh --seed",
        "sync-gh-actions-credentials.sh",
    ]


def test_without_credentials_the_credentials_step_is_skipped(tmp_path: Path) -> None:
    meta, secrets = fake_meta(tmp_path), tmp_path / "secrets"
    secrets.mkdir()
    fake = FakeExec()
    outcomes = reconcile("o", PLAN, meta, secrets, None, dry_run=False, exec_=fake)
    assert "sync-gh-actions-credentials.sh" not in fake.scripts()
    skipped = next(o for o in outcomes if o.name == "credentials")
    assert skipped.code is None
    assert "release-bot" in skipped.lines[0]


def test_drift_is_reported_with_its_lines(tmp_path: Path) -> None:
    meta, secrets = fake_meta(tmp_path), tmp_path / "secrets"
    secrets.mkdir()
    out = (
        "OK  meta  allow_merge_commit\nMANUAL  install the app\nDRIFT  x  (would fix)\n"
    )
    fake = FakeExec({"sync-gh-repo-settings.sh": 1}, out)
    outcomes = reconcile("o", PLAN, meta, secrets, CREDS, dry_run=False, exec_=fake)
    assert outcomes[0] == Outcome(
        "settings", 1, ["MANUAL  install the app", "DRIFT  x  (would fix)"]
    )


def test_usage_error_stops_the_run_with_the_output(tmp_path: Path) -> None:
    meta, secrets = fake_meta(tmp_path), tmp_path / "secrets"
    secrets.mkdir()
    fake = FakeExec({"sync-gh-repo-rulesets.sh": 2}, "bad conf: RULESETS")
    with pytest.raises(RuntimeError, match=r"exit 2.*bad conf: RULESETS"):
        reconcile("o", PLAN, meta, secrets, CREDS, dry_run=False, exec_=fake)
    assert len(fake.calls) == 2


@pytest.mark.xfail(strict=True)
def test_settings_make_main_every_repos_default_branch(tmp_path: Path) -> None:
    meta, secrets = fake_meta(tmp_path), tmp_path / "secrets"
    secrets.mkdir()
    fake = FakeExec()
    reconcile("o", PLAN, meta, secrets, CREDS, dry_run=False, exec_=fake)
    settings = Path(fake.calls[0][1]["SYNC_SETTINGS_CONF"]).read_text()
    assert '"default_branch|main|only:meta,session-memory"' in settings
    assert '"has_wiki|false|all"' in settings
