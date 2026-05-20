"""Tests for Slack utility functions."""
import sys
from pathlib import Path

# Add slack/src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils import extract_first_url, extract_urls, has_urls, get_image_files


class TestExtractUrls:
    """Test URL extraction from Slack messages."""

    def test_slack_formatted_url(self):
        urls = extract_urls("<https://lu.ma/example-event>")
        assert urls == ["https://lu.ma/example-event"]

    def test_slack_url_with_label(self):
        urls = extract_urls("<https://lu.ma/example|Example Event>")
        assert urls == ["https://lu.ma/example"]

    def test_multiple_urls(self):
        text = "Check <https://a.com> and <https://b.com>"
        urls = extract_urls(text)
        assert len(urls) == 2

    def test_no_urls(self):
        assert extract_urls("no links here") == []

    def test_raw_url_fallback(self):
        urls = extract_urls("visit https://example.com/event")
        assert urls == ["https://example.com/event"]


class TestExtractFirstUrl:
    def test_returns_first(self):
        assert extract_first_url("<https://first.com> <https://second.com>") == "https://first.com"

    def test_returns_none_when_empty(self):
        assert extract_first_url("no links") is None


class TestHasUrls:
    def test_true_for_slack_url(self):
        assert has_urls("<https://example.com>") is True

    def test_false_for_no_url(self):
        assert has_urls("plain text") is False


class TestGetImageFiles:
    def test_filters_images(self):
        files = [
            {"mimetype": "image/png", "url_private": "https://slack.com/img.png", "name": "img.png", "size": 1000},
            {"mimetype": "application/pdf", "url_private": "https://slack.com/doc.pdf", "name": "doc.pdf", "size": 2000},
            {"mimetype": "image/jpeg", "url_private": "https://slack.com/photo.jpg", "name": "photo.jpg", "size": 3000},
        ]
        images = get_image_files(files)
        assert len(images) == 2
        assert images[0]["filename"] == "img.png"
        assert images[1]["filename"] == "photo.jpg"

    def test_empty_list(self):
        assert get_image_files([]) == []

    def test_none_input(self):
        assert get_image_files(None) == []
