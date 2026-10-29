#!/usr/bin/env python3
# Copyright (c) 2026 The Brave Authors. All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at https://mozilla.org/MPL/2.0/.

"""Synthetic tests of capture tooling, not Android Auto runtime tests."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).with_name('collect_android_auto.sh')
MOCK_ADB = r'''
import json
import os
import signal
import sys

args = sys.argv[1:]
assert args[:2] == ['-s', 'test-a53'], args
with open(os.environ['MOCK_CALLS'], 'a') as output:
    output.write(json.dumps(args) + '\n')
args = args[2:]
if args == ['get-state']:
    print('device')
elif args[:2] == ['shell', 'getprop']:
    print('SYNTHETIC Galaxy A53')
elif args[:3] == ['shell', 'pm', 'path']:
    print('package:/data/app/mock/base.apk')
elif args[:1] == ['shell'] and args[1].startswith('sha256sum '):
    print(os.environ['MOCK_SHA'] + '  /data/app/mock/base.apk')
elif args[:1] == ['logcat']:
    print('SYNTHETIC logcat capture', flush=True)
    signal.pause()
else:
    print('SYNTHETIC snapshot')
'''


class CollectAndroidAutoTest(unittest.TestCase):
    def test_requires_explicit_serial_and_output(self):
        result = subprocess.run(['bash', str(SCRIPT)], capture_output=True)
        self.assertEqual(2, result.returncode)
        self.assertIn(b'Usage:', result.stderr)

    def run_capture(self, directory, sha_matches=True):
        mock = directory / 'adb'
        mock.write_text(f'#!{sys.executable}\n' + MOCK_ADB)
        mock.chmod(0o755)
        apk = directory / 'synthetic.apk'
        apk.write_bytes(b'SYNTHETIC APK')
        expected = hashlib.sha256(apk.read_bytes()).hexdigest()
        calls = directory / 'calls.jsonl'
        environment = dict(os.environ,
                           ADB=str(mock),
                           MOCK_CALLS=str(calls),
                           MOCK_SHA=expected if sha_matches else '0' * 64)
        result = subprocess.run(
            ['bash', str(SCRIPT), 'test-a53', str(directory / 'capture'),
             str(apk)],
            input='yes\n\n\nSYNTHETIC: runtime tests not performed\n',
            text=True,
            capture_output=True,
            env=environment,
            timeout=180)
        return result, [json.loads(line) for line in calls.read_text().splitlines()]

    def test_mismatched_apk_aborts_before_test(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            result, calls = self.run_capture(directory, sha_matches=False)
            self.assertEqual(2, result.returncode, result.stdout + result.stderr)
            self.assertIn('APK mismatch', result.stdout)
            self.assertFalse(any('logcat' in call for call in calls))
            self.assertFalse((directory / 'capture/observations.txt').exists())

    def test_capture_uses_serial_and_preserves_observations(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            result, calls = self.run_capture(directory)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            for stage in ('before', 'reference', 'brave', 'after'):
                self.assertTrue((directory / f'capture/{stage}-activities.txt').exists())
                self.assertTrue((directory / f'capture/{stage}-displays.txt').exists())
            self.assertEqual(
                'SYNTHETIC: runtime tests not performed\n',
                (directory / 'capture/observations.txt').read_text())
            self.assertTrue(all(call[:2] == ['-s', 'test-a53'] for call in calls))
            self.assertFalse(any(call[2] == 'install' or call[2:4] == ['shell', 'am']
                                 for call in calls))
            self.assertFalse(any('-c' in call for call in calls if 'logcat' in call))
            self.assertIn(['-s', 'test-a53', 'shell', 'log', '-t',
                           'BraveAutoTest', 'capture-complete'], calls)


if __name__ == '__main__':
    unittest.main()
