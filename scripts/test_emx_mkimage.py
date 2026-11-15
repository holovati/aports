"""Tests for emx-mkimage. Run: python3 -m unittest scripts/test_emx_mkimage.py -v"""

import importlib.machinery
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_path = Path(__file__).resolve().parent / "emx-mkimage"
_loader = importlib.machinery.SourceFileLoader("emx_mkimage", str(_path))
_spec = importlib.util.spec_from_loader("emx_mkimage", _loader)
mk = importlib.util.module_from_spec(_spec)
sys.modules["emx_mkimage"] = mk
_loader.exec_module(mk)


def write_aport(root, repo, name, depends="", makedepends="", subpackages="", extra=""):
    d = Path(root) / repo / name
    d.mkdir(parents=True)
    (d / "APKBUILD").write_text(
        f'pkgname={name}\npkgver=1.0\npkgrel=2\narch="all"\n'
        f'depends="{depends}"\nmakedepends="{makedepends}"\nsubpackages="{subpackages}"\n{extra}\n'
    )


class AportsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_reads_variables(self):
        write_aport(self.root, "main", "a", depends="b>=1.0 !c so:libx.so.1", subpackages="a-dev:dev a-doc")
        write_aport(self.root, "main", "b")
        aports = mk.Aports(self.root)
        a = aports.items["a"]
        self.assertEqual(a.version, "a-1.0-r2")
        self.assertEqual(a.depends, ["b"])
        self.assertEqual(a.subpackages, ["a-dev", "a-doc"])
        self.assertEqual(aports.owner["a-dev"], "a")

    def test_order_dependencies_first(self):
        write_aport(self.root, "main", "app", makedepends="lib", depends="rt")
        write_aport(self.root, "main", "lib", makedepends="tool")
        write_aport(self.root, "main", "tool")
        write_aport(self.root, "main", "rt")
        order, cycles = mk.Aports(self.root).order({"app"})
        names = [s.aport.key for s in order]
        self.assertEqual(cycles, [])
        self.assertLess(names.index("tool"), names.index("lib"))
        self.assertLess(names.index("lib"), names.index("app"))
        self.assertLess(names.index("rt"), names.index("app"))

    def test_makedepends_cycle_is_reported(self):
        write_aport(self.root, "main", "x", makedepends="y")
        write_aport(self.root, "main", "y", makedepends="x")
        order, cycles = mk.Aports(self.root).order({"x"})
        self.assertEqual(len(order), 2)
        self.assertEqual(len(cycles), 1)

    def test_runtime_cycle_is_silent(self):
        write_aport(self.root, "main", "x", depends="y")
        write_aport(self.root, "main", "y", depends="x")
        order, cycles = mk.Aports(self.root).order({"x"})
        self.assertEqual(len(order), 2)
        self.assertEqual(cycles, [])

    def test_split_makedepends_only_count_when_makedepends_is_empty(self):
        # abuild 3.16 calcdeps(): makedepends_build/host are used only if makedepends is empty
        write_aport(self.root, "main", "split", extra='makedepends_build="tool"\nmakedepends_host="lib"')
        write_aport(self.root, "main", "both", makedepends="lib", extra='makedepends_build="tool"')
        write_aport(self.root, "main", "tool")
        write_aport(self.root, "main", "lib")
        aports = mk.Aports(self.root)
        self.assertEqual(aports.items["split"].makedepends, ["tool", "lib"])
        self.assertEqual(aports.items["both"].makedepends, ["lib"])

    def test_cycle_is_built_in_two_passes(self):
        # curl needs brotli, brotli needs cmake, cmake needs curl; curl can leave brotli out
        write_aport(self.root, "main", "curl", makedepends="brotli", extra='[ -n "$APORTS_BOOTSTRAP" ] && makedepends=""')
        write_aport(self.root, "main", "brotli", makedepends="cmake")
        write_aport(self.root, "main", "cmake", makedepends="curl")
        steps, cycles = mk.Aports(self.root).order({"brotli"})
        self.assertEqual(cycles, [])
        self.assertEqual(
            [(s.aport.key, s.stage) for s in steps],
            [("curl", "bootstrap"), ("cmake", ""), ("brotli", ""), ("curl", "rebuild")],
        )
        self.assertEqual(steps[0].dropped, ["brotli"])
        self.assertEqual(steps[0].aport.makedepends, [])
        self.assertEqual(steps[3].aport.makedepends, ["brotli"])

    def test_bootstrap_variant_must_break_the_cycle(self):
        # x drops z, which is not part of the cycle x <-> y
        write_aport(self.root, "main", "x", makedepends="y z", extra='[ -n "$APORTS_BOOTSTRAP" ] && makedepends="y"')
        write_aport(self.root, "main", "y", makedepends="x")
        write_aport(self.root, "main", "z")
        steps, cycles = mk.Aports(self.root).order({"x"})
        self.assertEqual(len(cycles), 1)
        self.assertEqual({s.stage for s in steps}, {""})

    def test_two_pass_step_is_needed_until_the_rebuild_is_done(self):
        write_aport(self.root, "main", "curl", makedepends="brotli", extra='[ -n "$APORTS_BOOTSTRAP" ] && makedepends=""')
        write_aport(self.root, "main", "brotli", makedepends="cmake")
        write_aport(self.root, "main", "cmake", makedepends="curl")
        steps, _ = mk.Aports(self.root).order({"brotli"})
        first, rebuild = steps[0], steps[3]
        repo = self.root / "packages"
        self.assertTrue(first.needed(repo, False))
        self.assertTrue(rebuild.needed(repo, False))
        apk = repo / "main" / mk.ARCH / "curl-1.0-r2.apk"
        apk.parent.mkdir(parents=True)
        apk.touch()
        first.marker_path(repo).touch()  # the first pass has run
        self.assertFalse(first.needed(repo, False))
        self.assertTrue(rebuild.needed(repo, False))
        first.marker_path(repo).unlink()  # the rebuild has run
        self.assertFalse(rebuild.needed(repo, False))
        self.assertTrue(rebuild.needed(repo, True))

    def test_unbuildable_arch_is_skipped(self):
        write_aport(self.root, "main", "ok")
        d = self.root / "main" / "other"
        d.mkdir()
        (d / "APKBUILD").write_text('pkgname=other\npkgver=1\npkgrel=0\narch="aarch64"\n')
        self.assertEqual(set(mk.Aports(self.root).items), {"ok"})


class PlanTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        write_aport(self.root, "main", "base-pkg", depends="dep")
        write_aport(self.root, "main", "dep")
        write_aport(self.root, "main", "big", makedepends="dep-dev linux-headers")
        write_aport(self.root, "main", "dev-owner", subpackages="dep-dev")

    def test_missing_package_is_an_error(self):
        aports = mk.Aports(self.root)
        with self.assertRaises(mk.Error):
            mk.make_plan(aports, mk.Profile("p", packages=["nope"]), [], False)

    def test_all_makedepends(self):
        aports = mk.Aports(self.root)
        profile = mk.Profile("p", packages=["base-pkg"], all_makedepends=True)
        plan = mk.make_plan(aports, profile, [], False)
        self.assertIn("dep-dev", plan.install)
        self.assertEqual(plan.unresolved, ["linux-headers"])
        self.assertIn("dev-owner", [a.key for a in plan.order])
        self.assertNotIn("big", [a.key for a in plan.order])

    def test_ship_packages_builds_everything(self):
        aports = mk.Aports(self.root)
        plan = mk.make_plan(aports, mk.Profile("p", packages=["base-pkg"]), [], True)
        self.assertEqual({a.key for a in plan.order}, set(aports.items))

    def test_build_deps_split(self):
        aports = mk.Aports(self.root)
        found, unknown = mk.build_deps(aports, aports.items["big"])
        self.assertEqual(found, ["dep-dev"])
        self.assertEqual(unknown, ["linux-headers"])

    def test_stale_deps_reinstalls_other_versions(self):
        aports = mk.Aports(self.root)
        want = aports.items["dev-owner"]
        version = f"{want.pkgver}-r{want.pkgrel}"
        with mock.patch.object(mk, "apk_installed", return_value=True):
            with mock.patch.object(mk, "installed_versions", return_value={"dep-dev": version}):
                self.assertEqual(mk.stale_deps(aports, ["dep-dev"]), [])
            with mock.patch.object(mk, "installed_versions", return_value={"dep-dev": "0.1-r0"}):
                self.assertEqual(mk.stale_deps(aports, ["dep-dev"]), ["dep-dev"])
        with mock.patch.object(mk, "apk_installed", return_value=False), mock.patch.object(
            mk, "installed_versions", return_value={}
        ):
            self.assertEqual(mk.stale_deps(aports, ["dep-dev"]), ["dep-dev"])


class ProfileTest(unittest.TestCase):
    def test_shipped_profiles_load(self):
        base = mk.load_profile("base")
        builder = mk.load_profile("builder")
        self.assertTrue(set(base.packages) <= set(builder.packages))
        self.assertTrue(builder.first_boot_build)
        self.assertFalse(base.first_boot_build)

    def test_unknown_profile(self):
        with self.assertRaises(mk.Error):
            mk.load_profile("nope")

    def test_shipped_profiles_resolve_in_this_aports(self):
        aports = mk.Aports(_path.parent.parent)
        for name in mk.profile_names():
            mk.make_plan(aports, mk.load_profile(name), [], False)


class FirstBootTest(unittest.TestCase):
    def test_esp_gets_512_byte_clusters(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            (root / "boot/efi").mkdir(parents=True)
            with mock.patch.object(mk, "call") as call:
                mk.write_disk(root, Path(tmp) / "x.img", 64, 1 << 20)
            mkfs = next(c.args[0] for c in call.call_args_list if c.args[0][0] == "mkfs.vfat")
            self.assertEqual(mkfs[mkfs.index("-s") + 1], "1")
            self.assertEqual(mkfs[mkfs.index("-S") + 1], "512")

    def test_usr_layout_is_seeded_before_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mk.seed_usr_merge(root)
            for name in ("bin", "sbin", "lib"):
                self.assertTrue((root / "usr" / name).is_dir())
                self.assertEqual((root / name).readlink(), Path(f"usr/{name}"))
            mk.seed_usr_merge(root)  # idempotent

    def test_builder_writes_first_boot_build(self):
        import types

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "etc/apk").mkdir(parents=True)
            args = types.SimpleNamespace(
                hostname="h", dns=[], ip=None, root_password_hash=None, ssh_key=None, image_repo=[]
            )
            mk.configure_root(root, args, mk.load_profile("builder"))
            script = (root / "etc/rc.d/080-first-build.sh").read_text()
            self.assertIn("--build-all --no-image --register-repos --keep-deps", script)
            self.assertIn("first-build-done", script)
            self.assertTrue((root / "etc/rc.d/090-repohost.sh").exists())
            self.assertEqual((root / "etc/apk/repositories").read_text(), "")

    def test_base_has_no_first_boot_build(self):
        import types

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "etc/apk").mkdir(parents=True)
            args = types.SimpleNamespace(
                hostname="h", dns=[], ip=None, root_password_hash=None, ssh_key=None, image_repo=[]
            )
            mk.configure_root(root, args, mk.load_profile("base"))
            self.assertFalse((root / "etc/rc.d/080-first-build.sh").exists())


class ParseTest(unittest.TestCase):
    def test_size(self):
        self.assertEqual(mk.parse_size("32G"), 32 << 30)
        self.assertEqual(mk.parse_size("512m"), 512 << 20)

    def test_bad_size(self):
        with self.assertRaises(Exception):
            mk.parse_size("lots")


if __name__ == "__main__":
    unittest.main()
