Place official `openstf/minitouch` build outputs here.

Expected layout:

`bin/minitouch/libs/<abi>/minitouch`

Optional for SDK < 16:

`bin/minitouch/libs/<abi>/minitouch-nopie`

Packaged outputs produced by CI or `scripts/build_minitouch.sh` should also include:

`bin/minitouch/build-info.txt`
`bin/minitouch/LICENSE*`
`bin/minitouch/NOTICE*`

This mirrors the official repository build output after running `ndk-build`:
https://github.com/openstf/minitouch

Examples:

`bin/minitouch/libs/arm64-v8a/minitouch`
`bin/minitouch/libs/armeabi-v7a/minitouch`
`bin/minitouch/libs/x86_64/minitouch`

Notes:

- If you do not want to build locally, run `.github/workflows/build-minitouch.yml`
  and extract the `minitouch-openstf-binaries` artifact into the repository root.
- The release/nightly packaging workflows check the upstream repository head and
  rebuild this artifact when the upstream commit changes or the cached package
  is missing.
- Android 10+ requires STFService forwarding according to the official README.
- The current adapter only supports standalone minitouch mode for Android 9 and below.
