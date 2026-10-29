#!/usr/bin/env bash
# Copyright (c) 2026 The Brave Authors. All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at https://mozilla.org/MPL/2.0/.

# Read-only diagnostics, apart from adding log markers. Does not launch apps,
# clear logcat, spoof an installer, or alter host/parked-state settings.
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "Usage: bash $0 ADB_SERIAL OUTPUT_DIRECTORY [EXPECTED_BRAVE_APK]" >&2
  exit 2
fi

root=$(cd "$(dirname "$0")/../.." && pwd)
adb=${ADB:-"$root/../third_party/android_sdk/public/platform-tools/adb"}
serial=$1
output=$2
apk=${3:-}
brave=com.brave.browser_default
reference=${AA_REFERENCE_PACKAGE:-com.kododake.aabrowser}
if [[ ! $reference =~ ^[a-zA-Z0-9_]+(\.[a-zA-Z0-9_]+)+$ ]]; then
  echo "Invalid AA_REFERENCE_PACKAGE" >&2
  exit 2
fi
if [[ -e $output ]]; then
  echo "Use a new output directory to preserve previous captures." >&2
  exit 2
fi
"$adb" -s "$serial" get-state
mkdir -p "$output"
exec > >(tee "$output/session.txt") 2>&1

date -Is
echo "ADB serial: $serial"
"$adb" -s "$serial" shell getprop ro.product.model
"$adb" -s "$serial" shell getprop ro.build.version.release
"$adb" -s "$serial" shell getprop ro.build.version.sdk
echo "Confirm this is the Galaxy A53 used for the parked Android Auto test."
read -r -p "Type yes to continue: " answer
[[ $answer == yes ]] || exit 2

if [[ -n $apk ]]; then
  expected=$(sha256sum "$apk" | awk '{print $1}')
  base=$("$adb" -s "$serial" shell pm path "$brave" | tr -d '\r' | sed -n 's/^package:\(.*\/base.apk\)$/\1/p')
  if [[ -z $base || $base == *$'\n'* ]]; then
    echo "Could not identify a single installed Brave base.apk." >&2
    exit 2
  fi
  actual=$("$adb" -s "$serial" shell "sha256sum '$base'" | tr -d '\r' | awk '{print $1}')
  echo "Expected APK SHA-256: $expected"
  echo "Installed APK SHA-256: $actual"
  if [[ $expected != "$actual" ]]; then
    echo "APK mismatch (or installed APK unreadable). Do not test a stale build." >&2
    exit 2
  fi
fi

snapshot() {
  local stage=$1
  "$adb" -s "$serial" shell date > "$output/$stage-device-time.txt"
  for package in "$brave" "$reference" com.google.android.projection.gearhead; do
    "$adb" -s "$serial" shell dumpsys package "$package" > "$output/$stage-$package.txt"
    "$adb" -s "$serial" shell pm path "$package" > "$output/$stage-$package-paths.txt"
    "$adb" -s "$serial" shell cmd package query-activities --brief --components \
      -a android.intent.action.MAIN -c android.intent.category.CAR_LAUNCHER \
      -p "$package" > "$output/$stage-$package-car-activities.txt" 2>&1 || true
    "$adb" -s "$serial" shell cmd package resolve-activity --brief \
      -a android.intent.action.MAIN -c android.intent.category.LAUNCHER \
      -p "$package" > "$output/$stage-$package-phone-activity.txt" 2>&1 || true
    "$adb" -s "$serial" shell cmd package query-services --brief --components \
      -a android.media.browse.MediaBrowserService -p "$package" \
      > "$output/$stage-$package-media-services.txt" 2>&1 || true
  done
  "$adb" -s "$serial" shell dumpsys activity activities > "$output/$stage-activities.txt"
  "$adb" -s "$serial" shell dumpsys display > "$output/$stage-displays.txt"
  "$adb" -s "$serial" shell dumpsys window windows > "$output/$stage-windows.txt"
}

"$adb" -s "$serial" logcat -b all -v threadtime -T 1 > "$output/logcat.txt" 2>&1 &
log_pid=$!
trap 'kill "$log_pid" 2>/dev/null || true; wait "$log_pid" 2>/dev/null || true' EXIT
snapshot before
echo "Connect Android Auto with the vehicle safely parked; keep ADB connected (wireless if needed)."
echo "Launch AA Browser from the car launcher, leaving its UI on screen."
"$adb" -s "$serial" shell log -t BraveAutoTest reference-test-start
read -r -p "Press Enter while AA Browser is visible, or after its failure: " _
snapshot reference
echo "Launch Brave Debug from the car launcher, leaving its UI/error on screen."
"$adb" -s "$serial" shell log -t BraveAutoTest brave-test-start
read -r -p "Press Enter while Brave is visible, or after its failure (including absent icon): " _
snapshot brave
echo "If launch succeeds, test touch/address bar/HTTPS/back/close/reopen and three launches."
echo "Test normal phone browsing and Playlist too. Do not operate the test while driving."
read -r -p "Describe actual results, including the three launches and parked restrictions: " results
printf '%s\n' "$results" > "$output/observations.txt"
snapshot after
"$adb" -s "$serial" shell log -t BraveAutoTest capture-complete
echo "Saved $output. Review for personal information before sharing."
