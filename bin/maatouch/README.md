Place official `MaaAssistantArknights/MaaTouch` build outputs here.

Expected layout:

`bin/maatouch/maatouch`

Also accepted:

`bin/maatouch/maatouch.apk`
`bin/maatouch.apk`

Packaged outputs produced by CI or `scripts/build_maatouch.sh` should also include:

`bin/maatouch/build-info.txt`
`bin/maatouch/LICENSE*`
`bin/maatouch/NOTICE*`

The current adapter pushes the artifact to the device and starts it via `app_process`.

The release/nightly packaging workflows check the upstream repository head and
rebuild this artifact when the upstream commit changes or the cached package is
missing.

If you do not want to build locally, run `.github/workflows/build-maatouch.yml`
and extract the `maatouch-official-artifact` artifact into the repository root.

Official sources:

- https://github.com/MaaAssistantArknights/MaaTouch
- https://raw.githubusercontent.com/MaaAssistantArknights/MaaTouch/master/README.md
