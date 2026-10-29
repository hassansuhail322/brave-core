#!/usr/bin/env python3
# Copyright (c) 2026 The Brave Authors. All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at https://mozilla.org/MPL/2.0/.

"""Manifest regressions only; these tests do not establish host eligibility."""

from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET


SRC = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SRC / 'third_party'))
import jinja2  # pylint: disable=wrong-import-position

ANDROID = '{http://schemas.android.com/apk/res/android}'
BROWSER = 'org.chromium.chrome.browser.ChromeTabbedActivity'
PLAYLIST = 'com.brave.playlist.playback_service.VideoPlaybackService'
CAR = 'android.intent.category.CAR_LAUNCHER'


def render(channel, debug=True):
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(SRC),
        undefined=jinja2.StrictUndefined,
        line_comment_prefix='##',
        trim_blocks=True,
        lstrip_blocks=True)
    template = env.get_template('chrome/android/java/AndroidManifest.xml')
    return ET.fromstring(template.render(
        channel=channel,
        is_debug='true' if debug else 'false',
        enable_cardboard='true',
        enable_vr='true',
        enable_openxr='true',
        enable_arcore='true',
        is_desktop_android='false',
        enable_screen_capture='true',
        use_proprietary_codecs='true',
        enable_dav1d_decoder='true',
        enable_jxl_decoder='true',
        zygote_preload_class='org.chromium.content_public.app.ZygotePreload',
        manifest_package='com.brave.browser_default',
        target_sdk_version='37',
        library_name='chrome'))


class AndroidAutoManifestTest(unittest.TestCase):
    def test_debug_car_launcher_is_existing_phone_launcher(self):
        root = render('default')
        activities = [a for a in root.findall('application/*')
                      if any(c.get(ANDROID + 'name') == CAR
                             for c in a.findall('intent-filter/category'))]
        self.assertEqual(['com.google.android.apps.chrome.Main'],
                         [a.get(ANDROID + 'name') for a in activities])
        alias = activities[0]
        self.assertEqual(BROWSER, alias.get(ANDROID + 'targetActivity'))
        self.assertEqual('true', alias.get(ANDROID + 'exported'))
        car_filter = next(f for f in alias.findall('intent-filter')
                          if any(c.get(ANDROID + 'name') == CAR
                                 for c in f.findall('category')))
        self.assertIn('android.intent.category.LAUNCHER',
                      [c.get(ANDROID + 'name') for c in car_filter.findall('category')])
        activity = next(a for a in root.findall('application/activity')
                        if a.get(ANDROID + 'name') == BROWSER)
        self.assertEqual('singleTask', activity.get(ANDROID + 'launchMode'))
        self.assertEqual('true', activity.get(ANDROID + 'resizeableActivity'))
        self.assertEqual('game', root.find('application').get(ANDROID + 'appCategory'))

    def test_release_does_not_gain_game_category_or_car_entry(self):
        root = render('default', debug=False)
        self.assertIsNone(root.find('application').get(ANDROID + 'appCategory'))
        self.assertNotIn(CAR, [c.get(ANDROID + 'name') for c in root.iter('category')])

    def test_public_channels_do_not_gain_experimental_entry(self):
        for channel in ('stable', 'beta', 'dev', 'canary'):
            with self.subTest(channel=channel):
                self.assertIsNone(render(channel).find('application').get(ANDROID + 'appCategory'))
                self.assertNotIn(CAR, [c.get(ANDROID + 'name')
                                      for c in render(channel).iter('category')])

    def test_playlist_retains_original_private_boundary(self):
        services = render('default').findall('application/service')
        playlist = next(s for s in services if s.get(ANDROID + 'name') == PLAYLIST)
        self.assertEqual('false', playlist.get(ANDROID + 'exported'))
        self.assertIsNone(playlist.get(ANDROID + 'permission'))
        self.assertIn('android.media.browse.MediaBrowserService',
                      [a.get(ANDROID + 'name') for a in playlist.iter('action')])

    def test_no_media_navigation_or_driving_distraction_exemption(self):
        root = render('default')
        names = {e.get(ANDROID + 'name') for e in root.iter()}
        for name in ('com.google.android.gms.car.application',
                     'androidx.car.app.category.NAVIGATION',
                     'android.intent.category.APP_MAPS',
                     'androidx.car.app.ACCESS_SURFACE',
                     'androidx.car.app.MAP_TEMPLATES',
                     'distractionOptimized'):
            self.assertNotIn(name, names)

    def test_phone_launcher_still_targets_chromium_browser(self):
        aliases = render('default').findall('application/activity-alias')
        main = next(a for a in aliases
                    if a.get(ANDROID + 'name') == 'com.google.android.apps.chrome.Main')
        self.assertEqual(BROWSER, main.get(ANDROID + 'targetActivity'))
        self.assertIn('android.intent.category.LAUNCHER',
                      [c.get(ANDROID + 'name') for c in main.iter('category')])


if __name__ == '__main__':
    unittest.main()
