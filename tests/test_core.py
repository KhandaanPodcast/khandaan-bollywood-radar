import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from khandaan_radar.dedupe import canonical_url, deduplicate_stories
from khandaan_radar.briefing import render_briefing
from khandaan_radar.dashboard import render_dashboard
from khandaan_radar.models import Story, Submission
from khandaan_radar.scoring import rank_stories
from khandaan_radar.submissions import group_submissions, load_submissions, resolve_submission_source
from khandaan_radar.summarizer import fallback_editorial


class CoreTests(unittest.TestCase):
    def test_canonical_url_removes_tracking(self):
        self.assertEqual(
            canonical_url("https://www.example.com/a/?utm_source=x&id=2#top"),
            "https://example.com/a?id=2",
        )

    def test_story_deduplication_by_similar_title(self):
        stories = [
            Story("Aamir Khan announces a new film", "https://a.test/1", "news", score=2),
            Story("Aamir Khan announces new film", "https://b.test/2", "news", score=1),
        ]
        self.assertEqual(len(deduplicate_stories(stories)), 1)

    def test_listener_csv_and_grouping(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            csv_path = tmp_path / "listeners.csv"
            csv_path.write_text(
                "story_link,summary,source_platform,why_it_matters,submitter_name,credit_permission,patreon_member\n"
                "https://example.com/a?utm_source=x,Trailer reaction,YouTube,Big visual moment,Asha,yes,no\n"
                "https://example.com/a,Trailer reaction,YouTube,Patrons requested it,Dev,no,yes\n",
                encoding="utf-8",
            )
            result = group_submissions(load_submissions(str(csv_path), tmp_path))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].duplicate_count, 2)
        self.assertTrue(result[0].patreon_member)
        self.assertEqual(result[0].submitters, ["Asha"])
        self.assertEqual(result[0].recommendation, "reel")
        self.assertGreater(result[0].priority_score, 0)
        self.assertEqual(result[0].topic_category, "trailer / music / craft")

    def test_google_form_sheet_headers_and_missing_field_warnings(self):
        csv_text = (
            "Timestamp,Story Link: Example: https://www.reddit.com/...,Briefly explain what happened.,"
            'Source Platform,"Why is this interesting, controversial or worth discussing?",'
            "Your Name or Handle,Can We Credit You?,Patreon Member\n"
            "2026-06-21 10:00,https://example.com/story,Audience debate,Reddit,"
            'Strong discussion potential,Asha,"Yes, credit me",Yes\n'
            "2026-06-21 10:05,https://example.com/incomplete,,YouTube,Strong visuals,Dev,No,No\n"
        )
        response = Mock(text=csv_text)
        response.raise_for_status.return_value = None
        warnings = []
        sheet_url = "https://docs.google.com/spreadsheets/d/sheet-id/edit?gid=42"
        with patch("requests.get", return_value=response) as get:
            result = load_submissions(sheet_url, Path.cwd(), warnings=warnings)

        get.assert_called_once_with(
            "https://docs.google.com/spreadsheets/d/sheet-id/export?format=csv&gid=42",
            timeout=20,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].summary, "Audience debate")
        self.assertTrue(result[0].credit_permission)
        self.assertTrue(result[0].patreon_member)
        self.assertEqual(result[0].submitted_at, datetime(2026, 6, 21, 10, 0))
        self.assertEqual(
            warnings,
            ["Listener submission row 3 skipped; missing required fields: summary"],
        )

    def test_direct_google_sheet_csv_export_url_is_preserved(self):
        response = Mock(
            text=(
                "story_link,summary,source_platform,why_it_matters,submitter_name,"
                "credit_permission,patreon_member\n"
            )
        )
        response.raise_for_status.return_value = None
        export_url = "https://docs.google.com/spreadsheets/d/sheet-id/export?format=csv"
        with patch("requests.get", return_value=response) as get:
            self.assertEqual(load_submissions(export_url, Path.cwd()), [])
        get.assert_called_once_with(export_url, timeout=20)

    def test_missing_required_columns_warn_and_skip_source(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            csv_path = tmp_path / "listeners.csv"
            csv_path.write_text("story_link,summary\nhttps://example.com/story,Story\n", encoding="utf-8")
            warnings = []
            result = load_submissions(str(csv_path), tmp_path, warnings=warnings)

        self.assertEqual(result, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("missing required columns", warnings[0])
        self.assertIn("source_platform", warnings[0])

    def test_listener_submission_url_overrides_configured_csv(self):
        with patch.dict(os.environ, {"LISTENER_SUBMISSIONS_URL": "https://example.com/listeners.csv"}):
            self.assertEqual(
                resolve_submission_source("listener_submissions.csv"),
                "https://example.com/listeners.csv",
            )
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_submission_source("listener_submissions.csv"), "listener_submissions.csv")

    def test_listener_submissions_render_in_all_outputs(self):
        submission = Submission(
            "https://example.com/listener-story", "Listener story marker", "Google Form",
            "The audience wants this discussed", "Asha", True, True,
            priority_score=70, discussion_score=65, confidence_score=60,
            output_recommendation="Patreon Discussion", khandaan_take="The audience spotted this.",
            editorial_angle="Follow the audience question.", suggested_hook="Why this story?",
            suggested_patron_poll="Should we discuss it?", submitters=["Asha"],
        )
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            briefing = tmp_path / "briefing.md"
            dashboards = [
                tmp_path / "dashboard.html",
                tmp_path / "share_dashboard.html",
                tmp_path / "public" / "index.html",
            ]
            render_briefing(briefing, [], [], [], [submission], fallback_editorial())
            for output in dashboards:
                render_dashboard(output, [], [], [], [submission], self_contained=True, fetch_images=False)

            for output in [briefing, *dashboards]:
                text = output.read_text(encoding="utf-8")
                self.assertIn("Listener Submissions", text)
                self.assertIn("Listener story marker", text)

    def test_rule_based_story_scoring(self):
        story = Story(
            "Trailer earns praise and backlash from rival fandoms",
            "https://example.com/trailer",
            "X (manual)",
            summary="Fans love the visuals, but angry posts call it the worst teaser.",
        )
        ranked = rank_stories([story])
        self.assertGreater(ranked[0].priority_score, 0)
        self.assertEqual(ranked[0].topic_category, "fan culture / controversy")
        self.assertEqual(ranked[0].audience_temperature, "mixed")
        self.assertIn(ranked[0].output_recommendation, {"Reel", "Shorts", "Main Episode", "Patreon Discussion", "Newsletter", "Ignore"})
        self.assertIn("Fan War", ranked[0].badges)
        self.assertGreater(ranked[0].discussion_score, 0)
        self.assertGreater(ranked[0].controversy_score, 0)
        self.assertGreater(ranked[0].engagement_score, 0)
        self.assertGreater(ranked[0].confidence_score, 0)
        self.assertTrue(ranked[0].editorial_angle)
        self.assertTrue(ranked[0].suggested_hook)
        self.assertTrue(ranked[0].suggested_patron_poll)
        self.assertTrue(ranked[0].khandaan_take)

    def test_dashboard_badges(self):
        story = Story(
            "Rumour: casting changes for streaming film after box office result",
            "https://example.com/badges",
            "Google News",
            summary="An unconfirmed studio report discusses the release strategy.",
        )
        scored = rank_stories([story])[0]
        for badge in {"Industry Trend", "Film Release", "Streaming", "Casting", "Rumour", "Box Office"}:
            self.assertIn(badge, scored.badges)
        self.assertLess(scored.confidence_score, 76)

    def test_editorial_briefing_sections_render_offline(self):
        stories = rank_stories([
            Story(
                "Studio announces a major streaming deal",
                "https://example.com/deal",
                "X (manual)",
                summary="The industry deal could change release strategy.",
            )
        ])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "briefing.md"
            render_briefing(output, stories, [], [], [], fallback_editorial())
            text = output.read_text(encoding="utf-8")
        required = [
            "Executive Summary", "Khandaan Take", "Top 3 Stories to Discuss",
            "Best Patreon Discussion", "Best Reel and Shorts Ideas", "Main Episode Candidates",
            "Fan War Watch", "Industry Trend Watch", "Listener Submissions", "Ignore",
            "If We Recorded Tonight", "Discussion", "Priority", "Controversy",
            "Engagement", "Confidence", "Badges", "Output", "Editorial note",
            "Opening hook", "Patron poll",
        ]
        for heading in required:
            self.assertIn(heading, text)

    def test_briefing_sorts_by_discussion_score(self):
        lower_priority = Story("High discussion", "", "manual", priority_score=20, discussion_score=90, output_recommendation="Main Episode", khandaan_take="Talk about this.")
        higher_priority = Story("High priority", "", "manual", priority_score=95, discussion_score=40, output_recommendation="Newsletter", khandaan_take="Less to discuss.")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "briefing.md"
            render_briefing(output, [higher_priority, lower_priority], [], [], [], fallback_editorial())
            text = output.read_text(encoding="utf-8")
        shortlist = text.split("## 11. If We Recorded Tonight", 1)[1]
        self.assertLess(shortlist.index("High discussion"), shortlist.index("High priority"))

    def test_visual_dashboard_renders_locally(self):
        breaking = Story(
            "Big fan debate",
            "https://example.com/fans",
            "Google News",
            published_at=datetime.now(timezone.utc),
            priority_score=82,
            discussion_score=78,
            controversy_score=88,
            engagement_score=72,
            confidence_score=84,
            badges=["Fan War"],
            output_recommendation="Main Episode",
            khandaan_take="This is worth discussing.",
            editorial_angle="Find the real argument.",
            suggested_hook="What are fans actually debating?",
            suggested_patron_poll="Is this debate useful?",
            image_url="https://images.example.com/poster.jpg",
            trend_direction="up",
        )
        reel = Submission(
            "https://example.com/reel", "Trailer reaction", "YouTube", "Strong visual", "Asha", True, True,
            priority_score=70, discussion_score=64, controversy_score=20,
            engagement_score=80, confidence_score=68, badges=["Film Release"],
            output_recommendation="Reel", khandaan_take="The trailer has done its job.",
            editorial_angle="Judge the craft.", suggested_hook="Does the film look good?",
            suggested_patron_poll="Are you seated?",
        )
        ignored = Story("Unconfirmed casting", "", "manual", priority_score=20, discussion_score=25, output_recommendation="Ignore", khandaan_take="Wait for facts.")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dashboard.html"
            markdown = Path(directory) / "exports" / "briefing.md"
            render_dashboard(output, [breaking, ignored], [], [], [reel], markdown_path=markdown)
            text = output.read_text(encoding="utf-8")
        for value in (
            "If We Recorded Tonight", "Trending Stories", "Fan War Watch", "Listener Submissions",
            "Best Reel Opportunities", "Best Patreon Discussions", "Industry Trend Watch",
            "HIGH INTEREST", "FAN WAR", "PATREON", "BREAKING",
            "REEL IDEA", "PODCAST", "editorial-meta", "exports/briefing.md",
            "poster.jpg", "UP", "under 1h old", "Discussion", "Heat",
            "CONFIRMED SIGNAL", "Open source", "Copy podcast notes", "Copy reel idea",
            "Copy Patreon post", "data-copy-target", "PODCAST NOTES", "REEL IDEA",
            "PATREON POST", "fallbackCopy", "KHANDAAN", "BOLLYWOOD <em>RADAR</em>",
            "What Bollywood fans are talking about <em>this week</em>",
            "The stories, debates, fan wars and industry shifts shaping Bollywood this week. Powered by news, Reddit discussions, X conversations and audience submissions.",
            "Bollywood news, Bollywood Reddit, Bollywood gossip, Bollywood box office, Hindi cinema, Bollywood podcast, Khandaan Podcast, Bollywood discussions, Bollywood trends",
            "Khandaan Bollywood Radar combines news, fan discussions, Reddit conversations, X chatter and listener submissions to surface the Bollywood stories worth talking about.",
            "Produced by Khandaan: A Bollywood Podcast", "https://www.youtube.com/@KhandaanPodcast",
        ):
            self.assertIn(value, text)
        for retired in ("CONTENT PLANNING DASHBOARD", "All Ranked Stories", "Stories To Ignore"):
            self.assertNotIn(retired, text)
        self.assertNotIn("<script src=", text)

    def test_editorial_dashboard_section_ordering(self):
        discussion_lead = Story(
            "Discussion lead", "https://example.com/discussion", "manual",
            discussion_score=90, controversy_score=20, priority_score=70,
            output_recommendation="Main Episode", khandaan_take="Lead the show.",
        )
        controversy_lead = Story(
            "Controversy lead", "https://example.com/controversy", "manual",
            discussion_score=60, controversy_score=95, priority_score=65,
            output_recommendation="Main Episode", khandaan_take="Handle with care.",
        )
        older = Submission(
            "https://example.com/older", "Older suggestion", "Form", "Older", "A", True, False,
            discussion_score=80, output_recommendation="Main Episode", khandaan_take="Older take.",
            submitted_at=datetime(2026, 6, 19, 10, 0),
        )
        newer = Submission(
            "https://example.com/newer", "Newer suggestion", "Form", "Newer", "B", True, False,
            discussion_score=30, output_recommendation="Main Episode", khandaan_take="Newer take.",
            submitted_at=datetime(2026, 6, 21, 10, 0),
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dashboard.html"
            render_dashboard(output, [controversy_lead, discussion_lead], [], [], [older, newer])
            text = output.read_text(encoding="utf-8")

        trending = text.split('id="trending"', 1)[1].split('id="fan-war"', 1)[0]
        fan_war = text.split('id="fan-war"', 1)[1].split('id="listener-submissions"', 1)[0]
        listeners = text.split('id="listener-submissions"', 1)[1].split('id="reels"', 1)[0]
        self.assertLess(trending.index("Discussion lead"), trending.index("Controversy lead"))
        self.assertLess(fan_war.index("Controversy lead"), fan_war.index("Discussion lead"))
        self.assertLess(listeners.index("Newer suggestion"), listeners.index("Older suggestion"))

    def test_story_age_and_trend_heuristics(self):
        recent = Story(
            "Official trailer released",
            "https://example.com/new",
            "Google News",
            published_at=datetime.now(timezone.utc),
            summary="The studio confirmed the release.",
        )
        scored = rank_stories([recent])[0]
        self.assertEqual(scored.trend_direction, "new")
        self.assertEqual(scored.age_label, "under 1h old")

    def test_self_contained_share_dashboard(self):
        story = Story(
            "Shareable story", "https://example.com/source", "Google News",
            priority_score=70, discussion_score=65, confidence_score=75,
            output_recommendation="Main Episode", image_url="https://images.example.com/remote.jpg",
            khandaan_take="This travels well.", editorial_angle="Discuss it.",
            suggested_hook="Ready?", suggested_patron_poll="Yes or no?",
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "share_dashboard.html"
            render_dashboard(
                output, [story], [], [], [], self_contained=True, fetch_images=False,
                public_url="https://example.github.io/khandaan/",
            )
            text = output.read_text(encoding="utf-8")
        for marker in (
            "Share dashboard", "Download HTML", "shareDashboard", "downloadDashboard",
            "navigator.share", "https://example.github.io/khandaan/", 'rel="canonical"',
            "Static share edition", "@media (max-width:559px)", "@media (min-width:700px)", "viewport",
            '<title>Khandaan Bollywood Radar</title>', 'name="keywords"',
            'property="og:title"', 'name="twitter:description"',
        ):
            self.assertIn(marker, text)
        self.assertNotIn("images.example.com/remote.jpg", text)


if __name__ == "__main__":
    unittest.main()
