# emx-mkimage

`emx-mkimage` builds the packages in this aports tree with `abuild` and writes a bootable emerixx
disk image (GPT, ESP + ext2 root) from them. Only the Python standard library is used.

```
emx-mkimage <profile> [options]
```

Files in this directory:

| File | Purpose |
| --- | --- |
| `emx-mkimage` | the tool |
| `profiles.toml` | the profiles (`base`, `builder`) |
| `test_emx_mkimage.py` | unit tests |

## Requirements

- Building packages and images: run as root on emerixx. It needs `abuild`, `apk`, `parted`,
  `mkfs.vfat`, `mcopy`, `mke2fs` and `zstd` (or `xz`, see `--compress`). Fedora cannot build the
  packages, emerixx builds the software it runs.
- `--dry-run` only prints the plan and works anywhere with Python 3.11 or newer.
- `--no-image` needs only the build tools, not `parted`, `mcopy` and so on.

## Quick start

```sh
cd /root/aports/scripts

# What would happen? Nothing is built or written.
./emx-mkimage base --dry-run

# Build what the profile needs and write base.img.zst
./emx-mkimage base -o base.img --ssh-key ~/.ssh/id_ed25519.pub

# A static address and a root password hash instead of an ssh key
./emx-mkimage base -o base.img --ip 192.168.1.50 --gw 192.168.1.1 --dns 192.168.1.1 \
    --root-password-hash "$(openssl passwd -6)"
```

Root is locked in the image unless `--root-password-hash` or `--ssh-key` is given. Without `--ip`
the network is not configured.

Packages that are already built are skipped. Finished packages are kept when a build fails, so
fix the problem and run the same command again. `--force` rebuilds everything.

Packages go to `~/packages` (`$REPODEST` or `--repodest`), one repository per aports directory
(`~/packages/main`, `~/packages/extra`). Signing keys are in `~/.abuild`, a key is created on the
first run and its public half is copied to `/etc/apk/keys`.

## Profiles

Profiles are in `profiles.toml`.

| Profile | What it is |
| --- | --- |
| `base` | Boots to a login prompt, about what Debian's netinst gives you. Add the rest with `apk add`. |
| `builder` | `base` plus the toolchain and this aports tree in `/root/aports`. It does not build anything by itself, you run `emx-rebuild-all` after logging in. |

Keys of a profile:

| Key | Meaning |
| --- | --- |
| `description` | shown in the plan |
| `extends` | inherit packages and flags from another profile |
| `packages` | installed into the image, apk resolves their dependencies |
| `all_makedepends` | also install the makedepends of every aport (a machine that can build everything) |
| `ship_aports` | copy this checkout to `/root/aports` |
| `rebuild_script` | install `/usr/local/bin/emx-rebuild-all`, which builds every aport in the foreground. Nothing builds by itself, the image contains no `.apk` files |
| `serve_port` | serve `/root/packages` over HTTP on this port at boot (needs `python3`) |

Every name in `packages` must have an APKBUILD in this tree. The `kernel` and `emerixx-loader`
packages put `kernel.elf` and `BOOTX64.EFI` on the ESP, an image without them is refused.

### Add a profile

```toml
[dev]
description = "base plus a few tools"
extends = "base"
packages = ["gdb", "strace"]
```

Then `./emx-mkimage dev --dry-run`.

## Add a package to an image

Without touching a profile:

```sh
./emx-mkimage base --add htop --add tmux -o base.img
```

`--add` is repeatable. The package and everything it needs is built first when it is not in the
repository yet.

## Add a new package (aport)

1. Create `main/<name>/APKBUILD` (`extra/<name>/` for things that are not part of the system).
   The directory name must be the `pkgname`.

   ```sh
   # Maintainer: Your Name <you@example.org>

   pkgname=bc
   pkgver=1.08.2
   pkgrel=0
   pkgdesc="Arbitrary precision numeric processing language (calculator)"
   url="https://www.gnu.org/software/bc/bc.html"
   arch="all"
   license="GPL-3.0-or-later"
   options="!check"

   makedepends="bison flex readline texinfo"
   depends="readline"

   subpackages="$pkgname-doc"

   source="https://ftp.gnu.org/gnu/bc/bc-$pkgver.tar.gz"

   build() {
   	./configure \
   		--build=$CBUILD \
   		--host=$CHOST \
   		--prefix=/usr \
   		--sysconfdir=/etc \
   		--mandir=/usr/share/man
   	make
   }

   package() {
   	make DESTDIR="$pkgdir" install
   }

   sha512sums=""
   ```

2. Fill in the checksums. On emerixx, as root:

   ```sh
   cd main/bc && abuild -F checksum
   ```

3. Look at the plan, then build it:

   ```sh
   ./emx-mkimage base --add bc --dry-run
   ./emx-mkimage base --add bc --no-image
   ```

   `--no-image` builds the packages and stops. The result is in `~/packages/main/x86_64/`.

4. Commit and push. The builder image takes the tree from `/root/aports`, so `git pull` there.

Rules that matter here:

- Keep `options="!check"`. The tests are not run, every aport sets it.
- `makedepends` is what the build needs, `depends` is what the installed package needs at run
  time. Put build tools (`meson`, `autoconf`, `scdoc`, `util-macros`, ...) in `makedepends` only.
  If `makedepends` is empty, `makedepends_build` and `makedepends_host` are used instead, like
  abuild does. If it is not empty they are ignored.
- Names in `depends`/`makedepends` must be names of an aport or of one of its `subpackages`.
  `emx-mkimage` installs the makedepends itself and runs `abuild -d`, so names that emerixx does
  not have (`zlib-dev`, `build-base`, ...) are not wanted. Unknown names are listed as a warning in
  the plan and are not installed.
- Do not set `pkgusers`/`pkggroups`, the guest has no `getent` and `abuild-addgroup` while it
  builds.
- `arch="all"` or `arch="x86_64"`. An aport that does not list the machine's architecture is
  skipped.
- The `source` must be a URL that works. Local files (patches, config files) are listed next to
  the URLs and live in the aport directory.

### Change or update a package

Edit `pkgver`/`pkgrel`, run `abuild -F checksum`, commit. A package counts as built when
`<name>-<pkgver>-r<pkgrel>.apk` exists in the repository, so **bump `pkgrel` (or `pkgver`) for the
change to be built**, or use `--force`.

## Build order and the plan

`emx-mkimage` reads every APKBUILD, follows `makedepends` and `depends` and builds dependencies
first. `--dry-run` prints the result without building anything:

```
$ ./emx-mkimage builder --build-all --dry-run
== Profile builder: Toolchain and the aports tree, ...
== 152 packages to install, 187 in the repository, 188 to build
== 1 packages are built in two passes to break dependency cycles: curl
  ...
  curl-8.15.0-r1 (pass 1 of 2, without brotli nghttp2) build
  ...
  curl-8.15.0-r1 (pass 2 of 2, complete)       build
  libgpg-error-1.61-r0                         up to date
```

The plan takes about a minute, every APKBUILD is sourced by a shell.

### Dependency cycles

A cycle between makedepends (`curl` needs `brotli`, `brotli` needs `cmake`, `cmake` needs `curl`)
cannot be built in any order. The APKBUILD of one package in the cycle has to say which
dependencies it can do without. `emx-mkimage` sets `APORTS_BOOTSTRAP=1` for a first pass, builds
the package without them, builds the rest of the cycle, and then rebuilds the package in full:

```sh
if [ -z "$APORTS_BOOTSTRAP" ]; then
	_optdeps="brotli nghttp2"
	_with="--with"
else
	_optdeps=""
	_with="--without"
fi

depends="$_optdeps ca-certificates zlib zstd"
depends_dev="$_optdeps ca-certificates openssl zlib zstd"

build() {
	./configure ... $_with-nghttp2 $_with-brotli
	make
}
```

The first pass leaves a marker `<repo>/.bootstrap-<version>` in the repository. The second pass
runs as long as the marker exists, so an interrupted run continues where it stopped.

A cycle without such a variant is a warning in the plan, a package of the cycle must already be
built for it to work. The first pass package stays installed on the machine that built it, it is
not swapped for the final one because the version is the same. Images get the final one from the
repository.

## Build a builder

The `builder` profile is an image that builds the whole distribution itself, with no `.apk` in it.

1. On an emerixx machine, write the image:

   ```sh
   ./emx-mkimage builder -o builder.img \
       --hostname builder --ip 192.168.1.90 --gw 192.168.1.1 --dns 192.168.1.1 \
       --ssh-key ~/.ssh/id_ed25519.pub \
       --image-repo http://192.168.1.90:8080/main \
       --image-repo http://192.168.1.90:8080/extra
   ```

   This builds only what the profile installs (the toolchain). The image is `builder.img.zst`.

2. Decompress it and boot it:

   ```sh
   zstd -d builder.img.zst
   ```

3. Log in and run `emx-rebuild-all`. Nothing is built before that. It runs in the foreground and
   prints everything abuild says:

   ```sh
   emx-rebuild-all
   ```

   It is a wrapper for `emx-mkimage builder --build-all --no-image --register-repos --keep-deps`
   in `/root/aports/scripts`. It builds every aport and adds each finished repository to
   `/etc/apk/repositories`. To keep a log: `emx-rebuild-all 2>&1 | tee /var/log/rebuild-all.log`.

4. `/etc/rc.d/090-repohost.sh` serves `/root/packages` on port 8080, so other machines can use it
   as an apk repository (`http://builder:8080/main`).

If a package fails, abuild's error is the last thing on the terminal. Fix it in the aports tree,
`git pull` in `/root/aports` (or edit it there) and run `emx-rebuild-all` again, it only builds
what is missing.

Useful variations:

```sh
emx-rebuild-all --dry-run                # what is left to build
emx-rebuild-all --force                  # build everything again
emx-rebuild-all --pull                   # git pull --ff-only first
emx-rebuild-all --abuild-flags '-v'      # extra abuild flags
```

## Options

| Option | Meaning |
| --- | --- |
| `-o, --output FILE` | image file, default `<profile>.img` |
| `--aports DIR` | aports checkout, default the one this script is in |
| `--pull` | `git pull --ff-only` the aports first |
| `--repodest DIR` | where abuild puts packages, default `$REPODEST` or `~/packages` |
| `--add PKG` | install another package, repeatable |
| `--build-all` | build every aport, not only what the profile needs |
| `--no-image` | build the packages only |
| `--register-repos` | add each repository to `/etc/apk/repositories` as it gets filled |
| `--force` | rebuild packages that exist |
| `--abuild-flags` | extra flags for abuild |
| `--keep-deps` | keep the build dependencies installed after each package |
| `-n, --dry-run` | print the plan and stop |
| `--image-repo URL` | repository for `/etc/apk/repositories` in the image, repeatable |
| `--key FILE.pub` | public key the image trusts, repeatable. The keys in `/etc/apk/keys` are always included |
| `--untrusted` | `apk --allow-untrusted` |
| `--root-size SIZE` | root filesystem size, default 32G |
| `--esp-size MB` | ESP size in MiB, default 64 |
| `--hostname` | default `emerixx` |
| `--ip`, `--netmask`, `--gw`, `--dns`, `--iface` | static network, written to `/etc/emx/network.conf` (`--iface` default `en1`, `--netmask` default 255.255.255.0, `--dns` repeatable) |
| `--root-password-hash` | crypt(3) hash for root |
| `--ssh-key FILE.pub` | authorized key for root |
| `--compress zstd\|xz\|none` | default `zstd` |
| `--keep-raw` | keep the raw image after compressing |
| `--workdir DIR` | where the root tree is assembled, default `/var/tmp`, needs room for the whole image content |

The image has no apk repositories unless `--image-repo` is given (the `builder` profile uses its
own). `emx-mkimage` warns about it.

## Tests

```sh
cd scripts
python3 -m unittest test_emx_mkimage
```

## Troubleshooting

- `missing tools: ...`: install them, see Requirements.
- `build of <pkg> failed`: the abuild output above the message has the reason. Fix the APKBUILD
  and run the same command again.
- `cannot install the build dependencies of <pkg>`: a makedepends is not built yet or has no aport.
  Look at the plan, a dependency should come before the package.
- `packages signed with an unknown key moved to <repo>/untrusted`: a package in the repository is
  signed with a key that is gone. `emx-mkimage` moves such packages away and builds them again.
- A build directory that cannot be removed is reported as a warning and ignored.
