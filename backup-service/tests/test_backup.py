"""Tests for the backup service: pure transforms + orchestration (I/O faked)."""
import backup as bk


# --- pure transforms --------------------------------------------------------

def test_safe_ts_strips_colons_and_offset():
    assert bk._safe_ts("2026-06-16T03:00:00+00:00") == "2026-06-16T030000Z"
    assert bk._safe_ts("2026-06-16T03:00:00Z") == "2026-06-16T030000Z"


def test_dump_filename_layout():
    name = bk.dump_filename("farmos", "2026-06-16T03:00:00+00:00")
    assert name == "farmos__routine__2026-06-16T030000Z.dump"
    assert bk.db_label_of(name) == "farmos"
    snap = bk.dump_filename("farmos", "2026-06-16T03:00:00Z", reason="premigrate")
    assert "__premigrate__" in snap


def test_filenames_sort_chronologically():
    early = bk.dump_filename("farmos", "2026-06-16T03:00:00Z")
    late = bk.dump_filename("farmos", "2026-06-16T04:00:00Z")
    assert sorted([late, early]) == [early, late]


def test_prune_plan_keeps_newest_per_label():
    names = [
        bk.dump_filename("farmos", f"2026-06-1{d}T03:00:00Z") for d in range(1, 6)
    ] + [
        bk.dump_filename("postgis", f"2026-06-1{d}T03:00:00Z") for d in range(1, 6)
    ]
    doomed = bk.prune_plan(names, keep=2)
    # 5 each → 3 each pruned, newest 2 of each survive.
    assert len(doomed) == 6
    survivors = set(names) - set(doomed)
    assert bk.dump_filename("farmos", "2026-06-15T03:00:00Z") in survivors
    assert bk.dump_filename("farmos", "2026-06-11T03:00:00Z") in doomed


def test_prune_plan_keep_zero_never_deletes():
    names = [bk.dump_filename("farmos", "2026-06-16T03:00:00Z")]
    assert bk.prune_plan(names, keep=0) == []
    assert bk.prune_plan(names, keep=-1) == []


def test_prune_plan_ignores_non_dump_names():
    assert bk.prune_plan(["README.md", "notes.txt"], keep=1) == []


def test_s3_key():
    assert bk.s3_key("agriforestryos/backups", "x.dump") == "agriforestryos/backups/x.dump"
    assert bk.s3_key("/p/", "x.dump") == "p/x.dump"
    assert bk.s3_key("", "x.dump") == "x.dump"


# --- orchestration ----------------------------------------------------------

class FakeDumper:
    def __init__(self, fail_labels=()):
        self._fail = set(fail_labels)
    def dump(self, db):
        if db["label"] in self._fail:
            raise bk.BackupError("boom")
        return f"DUMP:{db['label']}".encode()


class FakeLocal:
    def __init__(self): self.files = {}
    def write(self, name, data): self.files[name] = data
    def list(self): return list(self.files)
    def delete(self, name): self.files.pop(name, None)


class FakeRemote:
    def __init__(self): self.objects = {}
    def put(self, key, data): self.objects[key] = data
    def list(self, prefix): return [k for k in self.objects if k.startswith(prefix)]
    def delete(self, key): self.objects.pop(key, None)


_DBS = [
    {"label": "farmos", "host": "db", "user": "u", "password": "p", "name": "farm"},
    {"label": "postgis", "host": "postgis", "user": "u", "password": "p", "name": "gis"},
]


def _clock(t="2026-06-16T03:00:00Z"):
    return lambda: t


def test_run_once_dumps_both_local_and_remote():
    local, remote = FakeLocal(), FakeRemote()
    svc = bk.BackupService(FakeDumper(), local, remote, _DBS, keep=14, clock=_clock())
    counts = svc.run_once()
    assert counts["dumped"] == 2 and counts["uploaded"] == 2
    assert set(local.files) == {
        "farmos__routine__2026-06-16T030000Z.dump",
        "postgis__routine__2026-06-16T030000Z.dump",
    }
    assert local.files == {k.rsplit("/", 1)[-1]: v for k, v in remote.objects.items()}


def test_run_once_local_only_when_no_remote():
    local = FakeLocal()
    svc = bk.BackupService(FakeDumper(), local, None, _DBS, clock=_clock())
    counts = svc.run_once()
    assert counts["dumped"] == 2 and counts["uploaded"] == 0


def test_run_once_one_db_failure_does_not_abort_other():
    local = FakeLocal()
    svc = bk.BackupService(FakeDumper(fail_labels=["postgis"]), local, None, _DBS,
                           clock=_clock())
    counts = svc.run_once()
    assert counts["dumped"] == 1 and counts["failed"] == 1
    assert "farmos__routine__2026-06-16T030000Z.dump" in local.files


def test_run_once_prunes_old_local_and_remote():
    local, remote = FakeLocal(), FakeRemote()
    # Seed 3 old farmos dumps; keep=1 should leave only the newest after this pass.
    for d in (10, 11, 12):
        name = bk.dump_filename("farmos", f"2026-06-{d}T03:00:00Z")
        local.files[name] = b"old"
        remote.objects[bk.s3_key("agriforestryos/backups", name)] = b"old"
    svc = bk.BackupService(FakeDumper(), local, remote, [_DBS[0]], keep=1,
                           clock=_clock("2026-06-16T03:00:00Z"))
    counts = svc.run_once()
    # New dump is newest; everything older pruned in both stores.
    assert list(local.files) == ["farmos__routine__2026-06-16T030000Z.dump"]
    assert [k.rsplit("/", 1)[-1] for k in remote.objects] == [
        "farmos__routine__2026-06-16T030000Z.dump"]
    assert counts["pruned_local"] == 3 and counts["pruned_remote"] == 3


def test_reason_tag_flows_into_filename():
    local = FakeLocal()
    bk.BackupService(FakeDumper(), local, None, [_DBS[0]],
                     clock=_clock()).run_once(reason="premigrate")
    assert "farmos__premigrate__2026-06-16T030000Z.dump" in local.files
