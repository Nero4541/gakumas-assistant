# Third-Party Binary Notices

`bin/` may contain optional third-party binaries redistributed with Gakumas
Assistant. Copyright and trademark rights remain with their respective
upstream authors.

## Android Touch Resources

- `bin/maatouch/`
  - Source: `MaaAssistantArknights/MaaTouch`
  - Build metadata: `bin/maatouch/build-info.txt`
  - Upstream `LICENSE*` and `NOTICE*` files, when present, are copied into the
    same directory during CI packaging or by `scripts/build_maatouch.sh`.

- `bin/minitouch/`
  - Source: `openstf/minitouch`
  - Build metadata: `bin/minitouch/build-info.txt`
  - Upstream `LICENSE*` and `NOTICE*` files, when present, are copied into the
    same directory during CI packaging or by `scripts/build_minitouch.sh`.

## Other Bundled Binaries

- `bin/scrcpy-server-*`
  - Source: official `Genymobile/scrcpy` server artifact
  - Redistribution terms: follow the upstream project license and release notes.

- `bin/DroidCast-debug-1.2.1.apk`
  - Source: official `rayworks/DroidCast` artifact
  - Redistribution terms: follow the upstream project license and release notes.
