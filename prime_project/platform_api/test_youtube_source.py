import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings

from . import youtube_source as source


CHANNEL = "UC" + "a" * 22
VIDEO = "AbcDefGh_12"


def response(data=None, status=200, chunks=None):
    result = Mock(status_code=status)
    result.json.return_value = data
    result.iter_content.return_value = chunks or []
    return result


@override_settings(YOUTUBE_API_KEY="test-key-not-real")
class YouTubeProviderTests(SimpleTestCase):
    def setUp(self):
        self.get = patch.object(source.requests, "get").start()
        self.post = patch.object(source.requests, "post").start()
        self.addCleanup(patch.stopall)

    def channel_payload(self):
        return {"items": [{"id": CHANNEL, "snippet": {"title": "Creator"}, "contentDetails": {"relatedPlaylists": {"uploads": "UU" + "a" * 22}}}]}

    def snippet(self):
        return {"title": "Creative work", "description": "Details", "publishedAt": "2026-10-01T12:00:00Z", "channelId": CHANNEL,
                "thumbnails": {"high": {"url": "https://i.ytimg.com/vi/test/hqdefault.jpg"}}}

    def tab_item(self, video_id=VIDEO, *, legacy=False, shorts=False):
        endpoint = {"commandMetadata": {"webCommandMetadata": {"url": f"/shorts/{video_id}" if shorts else f"/watch?v={video_id}"}}}
        if legacy:
            content = {"videoRenderer": {"videoId": video_id, "navigationEndpoint": endpoint}}
        else:
            content = {"lockupViewModel": {"contentId": video_id, "contentType": "LOCKUP_CONTENT_TYPE_VIDEO",
                       "rendererContext": {"commandContext": {"onTap": {"innertubeCommand": endpoint}}}}}
        return {"richItemRenderer": {"content": content}}

    def tab_page(self, items=None, *, selected="Videos", sort="Latest", channel=CHANNEL, legacy=False):
        header = {"chipBarViewModel": {"chips": [{"chipViewModel": {"text": sort, "selected": True}}]}}
        if legacy:
            header = {"feedFilterChipBarRenderer": {"contents": [{"chipCloudChipRenderer": {"text": {"simpleText": sort}, "isSelected": True}}]}}
        grid = {"contents": [self.tab_item()] if items is None else items, "header": header}
        tab = {"tabRenderer": {"title": selected, "selected": True,
               "endpoint": {"commandMetadata": {"webCommandMetadata": {"url": f"/@creator/{selected.lower()}"}}},
               "content": {"richGridRenderer": grid}}}
        payload = {"metadata": {"channelMetadataRenderer": {"externalId": channel}},
                   "contents": {"twoColumnBrowseResultsRenderer": {"tabs": [tab]}}}
        return '<script>var ytInitialData = ' + json.dumps(payload) + ';</script>'

    def test_latest_video_reads_one_videos_page_then_one_api_video(self):
        page = self.tab_page([self.tab_item(shorts=True), self.tab_item(), self.tab_item("OlderVideo1")])
        self.get.side_effect = [response(chunks=[page.encode()]), response({"items": [{"id": VIDEO, "snippet": self.snippet(), "status": {"privacyStatus": "public"}}]})]
        result = source.latest_regular_video(CHANNEL)
        self.assertEqual(result["video_id"], VIDEO)
        self.assertEqual(self.get.call_count, 2)
        call = self.get.call_args_list[0]
        self.assertEqual(call.args[0], f"https://www.youtube.com/channel/{CHANNEL}/videos")
        self.assertFalse(call.kwargs["allow_redirects"])
        self.assertNotIn("key", call.kwargs["params"])
        self.assertEqual(self.get.call_args.kwargs["params"]["id"], VIDEO)

    def test_videos_tab_accepts_both_current_and_previous_renderers(self):
        for legacy in (True, False):
            with self.subTest(legacy=legacy):
                self.assertEqual(source._latest_video_id(self.tab_page([self.tab_item(legacy=legacy)], legacy=legacy), CHANNEL), VIDEO)

    def test_shorts_shelves_and_short_items_are_not_candidates(self):
        items = [{"richSectionRenderer": {"content": {"richShelfRenderer": {"contents": [self.tab_item("ShortVideo1")]}}}},
                 {"richItemRenderer": {"content": {"shortsLockupViewModel": {"videoId": "ShortVideo1"}}}},
                 self.tab_item("ShortVideo1", shorts=True), self.tab_item()]
        self.assertEqual(source._latest_video_id(self.tab_page(items), CHANNEL), VIDEO)

    def test_unknown_tab_sort_channel_or_schema_never_falls_back_to_uploads(self):
        pages = [self.tab_page(selected="Shorts"), self.tab_page(selected="Home"), self.tab_page(sort="Popular"),
                 self.tab_page(channel="UC" + "b" * 22), self.tab_page([{"unknownRenderer": {}}]),
                 '<html>Consent required</html>', 'var ytInitialData = {broken}',
                 'var ytInitialData = ' + '[' * 1100 + ']' * 1100]
        for page in pages:
            with self.subTest(page=page[:100]), self.assertRaisesMessage(source.ProviderError, "Videos tab"):
                source._latest_video_id(page, CHANNEL)

    def test_empty_videos_tab_returns_none_without_api_calls(self):
        self.get.return_value = response(chunks=[self.tab_page([]).encode()])
        self.assertIsNone(source.latest_regular_video(CHANNEL))
        self.assertEqual(self.get.call_count, 1)

    def test_videos_page_redirects_timeouts_and_size_are_bounded(self):
        for result in (response(status=302), response(chunks=[b'x' * (source.MAX_CHANNEL_PAGE_BYTES + 1)])):
            self.get.return_value = result
            with self.assertRaisesMessage(source.ProviderError, "Videos tab"):
                source.latest_regular_video(CHANNEL)
            result.close.assert_called_once()
        self.get.side_effect = requests.Timeout("private details")
        with self.assertRaises(source.ProviderError) as caught:
            source.latest_regular_video(CHANNEL)
        self.assertNotIn("private", str(caught.exception))

    def test_invalid_channel_never_becomes_a_request_url(self):
        with self.assertRaises(source.ProviderError):
            source.latest_regular_video("../evil?key=secret")
        self.get.assert_not_called()

    def test_latest_upcoming_video_is_not_imported_or_replaced_with_older_video(self):
        self.get.side_effect = [response(chunks=[self.tab_page().encode()]), response({"items": [{"id": VIDEO,
            "snippet": {**self.snippet(), "liveBroadcastContent": "upcoming"}, "status": {"privacyStatus": "public"}}]})]
        self.assertIsNone(source.latest_regular_video(CHANNEL))
        self.assertEqual(self.get.call_count, 2)

    def test_selected_video_must_belong_to_channel_and_be_public(self):
        for snippet, status in (({**self.snippet(), "channelId": "UC" + "b" * 22}, "public"), (self.snippet(), "private")):
            self.get.side_effect = [response(chunks=[self.tab_page().encode()]), response({"items": [{"id": VIDEO, "snippet": snippet, "status": {"privacyStatus": status}}]})]
            with self.assertRaises(source.ProviderError):
                source.latest_regular_video(CHANNEL)

    def test_handle_resolution_uses_channels_without_search_or_arbitrary_url(self):
        self.get.return_value = response(self.channel_payload())
        self.assertEqual(source.resolve_channel("https://www.youtube.com/@creator")["channel_id"], CHANNEL)
        self.assertEqual(self.get.call_args.args, (source.API_ROOT + "channels",))
        self.assertEqual(self.get.call_args.kwargs["params"]["forHandle"], "@creator")
        self.assertFalse(self.get.call_args.kwargs["allow_redirects"])

    def test_channel_id_and_legacy_username_selectors(self):
        self.get.return_value = response(self.channel_payload())
        source.resolve_channel("https://youtube.com/channel/" + CHANNEL)
        self.assertEqual(self.get.call_args.kwargs["params"]["id"], CHANNEL)
        source.resolve_channel("https://youtube.com/user/creator")
        self.assertEqual(self.get.call_args.kwargs["params"]["forUsername"], "creator")

    def test_untrusted_hosts_credentials_ports_and_old_custom_paths_rejected(self):
        for url in ("https://youtube.com.evil.test/@creator", "https://evil.test/youtube.com/@creator", "https://name:secret@youtube.com/@creator", "https://youtube.com:999/@creator", "file:///etc/passwd", "https://youtube.com/c/creator", "https://youtube.com/watch?v=" + VIDEO):
            with self.subTest(url=url), self.assertRaises(source.ProviderError):
                source.resolve_channel(url)
        self.get.assert_not_called()

    @override_settings(YOUTUBE_API_KEY="")
    def test_missing_key_is_actionable_without_network(self):
        with self.assertRaisesMessage(source.ProviderError, "YOUTUBE_API_KEY"):
            source.resolve_channel("https://youtube.com/@creator")
        self.get.assert_not_called()

    def test_quota_error_does_not_leak_upstream_details(self):
        self.get.return_value = response({"error": {"message": "secret-token", "errors": [{"reason": "quotaExceeded"}]}}, 403)
        with self.assertRaises(source.ProviderError) as caught:
            source.resolve_channel("https://youtube.com/@creator")
        self.assertIn("quota", str(caught.exception))
        self.assertNotIn("secret", str(caught.exception))

    def test_network_error_is_redacted(self):
        self.get.side_effect = requests.Timeout("API URL with secret-key")
        with self.assertRaises(source.ProviderError) as caught:
            source.resolve_channel("https://youtube.com/@creator")
        self.assertNotIn("secret", str(caught.exception))

    def test_malformed_or_empty_channel_response(self):
        for payload in (None, [], {"items": "wrong"}, {"items": []}, {"items": [{"id": CHANNEL}]}):
            self.get.return_value = response(payload)
            with self.subTest(payload=payload), self.assertRaises(source.ProviderError):
                source.resolve_channel("https://youtube.com/@creator")

    def test_video_urls_resolve_same_id_and_channel(self):
        self.get.return_value = response({"items": [{"id": VIDEO, "snippet": self.snippet(), "status": {"privacyStatus": "public"}}]})
        for url in (f"https://youtube.com/watch?v={VIDEO}&t=10", f"https://youtu.be/{VIDEO}", f"https://youtube.com/shorts/{VIDEO}"):
            data = source.fetch_video(url)
            self.assertEqual(data["video_id"], VIDEO)
            self.assertEqual(data["channel_id"], CHANNEL)

    def test_video_wrong_host_or_invalid_id_never_fetched(self):
        for url in ("https://youtu.be.evil.test/" + VIDEO, "https://youtube.com/watch?v=bad", "https://youtube.com/watch?v=" + VIDEO + "&v=OtherVideo1"):
            with self.assertRaises(source.ProviderError):
                source.fetch_video(url)
        self.get.assert_not_called()

    @override_settings(YOUTUBE_BLOG_CREDENTIALS_FILE="")
    def test_captions_require_owner_authorization_not_api_key(self):
        with self.assertRaisesMessage(source.ProviderError, "owner"):
            source.fetch_transcript(VIDEO)
        self.get.assert_not_called()
        self.post.assert_not_called()

    def test_oauth_refresh_uses_private_file_and_fixed_token_endpoint(self):
        with TemporaryDirectory() as directory:
            file = Path(directory) / "credentials.json"
            file.write_text(json.dumps({"client_id": "client", "client_secret": "secret", "refresh_token": "refresh"}), encoding="utf-8")
            self.post.return_value = response({"access_token": "access"})
            with override_settings(YOUTUBE_BLOG_CREDENTIALS_FILE=str(file)):
                self.assertEqual(source._access_token(), "access")
        self.assertEqual(self.post.call_args.args, (source.TOKEN_URL,))
        self.assertEqual(self.post.call_args.kwargs["data"]["grant_type"], "refresh_token")
        self.assertFalse(self.post.call_args.kwargs["allow_redirects"])

    def test_caption_download_selects_language_and_normalizes_subtitles(self):
        tracks = {"items": [{"id": "track", "snippet": {"language": "en", "status": "serving", "isDraft": False, "trackKind": "standard"}}]}
        self.get.side_effect = [response(tracks), response(chunks=[b"1\n00:00:01,000 --> 00:00:02,000\nHello creator.\n"])]
        with patch.object(source, "_access_token", return_value="access"):
            self.assertEqual(source.fetch_transcript(VIDEO), "Hello creator.")
        self.assertEqual(self.get.call_args.kwargs["params"], {"tfmt": "srt"})
        self.assertEqual(self.get.call_args.kwargs["headers"]["Authorization"], "Bearer access")

    def test_caption_forbidden_or_missing_is_explicit(self):
        with patch.object(source, "_access_token", return_value="access"):
            self.get.return_value = response({}, 403)
            with self.assertRaisesMessage(source.ProviderError, "access was denied"):
                source.fetch_transcript(VIDEO)
            self.get.return_value = response({"items": []})
            with self.assertRaisesMessage(source.ProviderError, "No ready captions"):
                source.fetch_transcript(VIDEO)

    def test_caption_download_size_is_bounded(self):
        tracks = {"items": [{"id": "track", "snippet": {"language": "en", "status": "serving"}}]}
        self.get.side_effect = [response(tracks), response(chunks=[b"x" * (source.MAX_TRANSCRIPT_BYTES + 1)])]
        with patch.object(source, "_access_token", return_value="access"), self.assertRaisesMessage(source.ProviderError, "limit"):
            source.fetch_transcript(VIDEO)

    def test_normalization_keeps_plain_script_and_removes_vtt_timing(self):
        self.assertEqual(source.normalize_transcript("# Heading\r\n\r\nA paragraph."), "# Heading\n\nA paragraph.")
        text = "WEBVTT\n\ncue-1\n00:01.000 --> 00:02.000 align:start\n<v Speaker>Hello &amp; welcome.</v>\n"
        self.assertEqual(source.normalize_transcript(text), "Hello & welcome.")

    def test_malformed_credential_file_never_leaks_values(self):
        with TemporaryDirectory() as directory:
            file = Path(directory) / "credentials.json"
            file.write_text('{"client_secret":"private"}', encoding="utf-8")
            with override_settings(YOUTUBE_BLOG_CREDENTIALS_FILE=str(file)), self.assertRaises(source.ProviderError) as caught:
                source._access_token()
        self.assertNotIn("private", str(caught.exception))
