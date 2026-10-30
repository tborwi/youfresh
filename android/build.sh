#!/usr/bin/env bash
# Builds the YouFresh Google TV app in Docker (no Android Studio needed).
# Output: android/YouFresh.apk. Signed with your key if android/keystore.properties exists,
# otherwise with a throwaway debug key (fine for trying it out; updates then need an uninstall).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p .cache
GV=8.11.1
EXTRA=()
if [ -f keystore.properties ]; then
  KS=$(sed -n 's/^storeFile=//p' keystore.properties)
  EXTRA=(-v "$KS":"$KS":ro)
fi
docker run --rm -u "$(id -u):$(id -g)" \
  -e GRADLE_USER_HOME=/cache/gradle -e HOME=/cache \
  -v "$PWD":/src -v "$PWD/.cache":/cache "${EXTRA[@]}" -w /src \
  ghcr.io/cirruslabs/android-sdk:35 bash -c "
    set -e
    if [ ! -x /cache/gradle-$GV/bin/gradle ]; then
      curl -fsSL -o /cache/g.zip https://services.gradle.org/distributions/gradle-$GV-bin.zip
      cd /cache && unzip -q g.zip && rm g.zip && cd /src
    fi
    echo sdk.dir=\$ANDROID_HOME > local.properties
    /cache/gradle-$GV/bin/gradle --no-daemon -q assembleRelease
  "
cp app/build/outputs/apk/release/app-release.apk YouFresh.apk
echo "Built $(pwd)/YouFresh.apk"
