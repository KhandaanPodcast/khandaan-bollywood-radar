import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from khandaan_radar.dedupe import canonical_url, deduplicate_stories
from khandaan_radar.briefing import render_briefing
from khandaan_radar.cli import build_parser, publish_root_homepage
from khandaan_radar.dashboard import render_dashboard
from khandaan_radar.models import Story, Submission
from khandaan_radar.fetchers import _google_news_query, _is_bollywood_relevant, _is_low_information_result
from khandaan_radar.intelligence import enrich_story_intelligence
from khandaan_radar.config import load_config
from khandaan_radar.scoring import rank_stories, select_diverse_stories
from khandaan_radar.submissions import group_submissions, load_submissions, resolve_submission_source
from khandaan_radar.summarizer import fallback_editorial


class CoreTests(unittest.TestCase):
    def test_public_homepage_is_copied_to_site_root(self):
        self.assertEqual(build_parser().parse_args([]).root_output, "index.html")
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            public_output = tmp_path / "public" / "index.html"
            root_output = tmp_path / "index.html"
            public_output.parent.mkdir()
            public_output.write_text("<html>dashboard</html>", encoding="utf-8")

            publish_root_homepage(public_output, root_output)

            self.assertEqual(root_output.read_bytes(), public_output.read_bytes())

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
        deduplicated = deduplicate_stories(stories)
        self.assertEqual(len(deduplicated), 1)
        self.assertEqual(deduplicated[0].metadata["source_count"], 2)

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
                self.assertIn("From the Khandaan Audience", text)
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

    def test_recording_prep_config_excludes_x_and_sets_requested_sources(self):
        config, _ = load_config(Path(__file__).parents[1] / "sources.yaml")
        self.assertFalse(config["x_inputs"]["enabled"])
        self.assertEqual(config["briefing"]["top_stories"], 15)
        self.assertIn("IndianCinema", config["reddit"]["subreddits"])
        self.assertIn("Prime Video India Bollywood", config["google_news"]["keywords"])
        releases = {item["title"]: item for item in config["watchlists"]["active_releases"]}
        self.assertEqual(releases["VVan"]["priority"], "P1")
        self.assertEqual(releases["Welcome to the Jungle"]["priority"], "P2")
        self.assertIn("Franchise fatigue", [item["name"] for item in config["watchlists"]["industry_themes"]])

    def test_watchlist_match_boosts_and_explains_ranking(self):
        watched = Story("Ramayana production update", "https://example.com/watched", "Google News")
        unwatched = Story("Unrelated production update", "https://example.com/unwatched", "Google News")
        ranked = rank_stories([unwatched, watched], ["Ramayana"])
        self.assertEqual(ranked[0].title, watched.title)
        self.assertEqual(ranked[0].metadata["watchlist_matches"], ["Ramayana"])
        self.assertIn("watchlist: Ramayana", ranked[0].ranking_reasons)

    def test_structured_watchlist_priorities_and_stale_penalty(self):
        watchlists = {
            "active_releases": [
                {"title": "VVan", "priority": "P1"},
                {"title": "Welcome to the Jungle", "priority": "P2"},
            ],
            "studios": [], "talent": [], "industry_themes": [],
            "ignore": [{"title": "Saiyaara", "penalty": 20}],
            "false_positive_exclusions": [],
        }
        stories = rank_stories([
            Story("VVan production update", "https://example.com/vvan", "Google News"),
            Story("Welcome to the Jungle production update", "https://example.com/welcome", "Google News"),
            Story("Saiyaara retrospective", "https://example.com/saiyaara", "Google News"),
        ], watchlists)
        self.assertEqual(stories[0].title, "VVan production update")
        self.assertEqual(stories[-1].title, "Saiyaara retrospective")
        self.assertIn("release: VVan (P1)", stories[0].metadata["watchlist_matches"])

    def test_why_khandaan_should_care_is_metadata_based_and_two_sentences(self):
        story = Story(
            "Superstar sequel faces audience backlash after weak box office opening",
            "https://example.com/debate",
            "Google News",
        )
        scored = rank_stories([story])[0]
        self.assertIn("fan-war potential", scored.why_khandaan_should_care)
        self.assertIn("box-office narratives", scored.why_khandaan_should_care)
        self.assertLessEqual(scored.why_khandaan_should_care.count("."), 2)

    def test_story_intelligence_uses_dashboard_relationships_and_source_counts(self):
        now = datetime.now(timezone.utc)
        news = rank_stories([Story(
            "Shah Rukh Khan sequel faces box office backlash",
            "https://example.com/news",
            "Google News",
            summary="The confirmed sequel opening prompted audience debate.",
            published_at=now,
            metadata={"source_count": 3},
        )])[0]
        reddit = rank_stories([Story(
            "Audience debates Shah Rukh Khan sequel box office",
            "https://reddit.com/r/bollywood/comments/1",
            "Reddit",
            summary="Fans discuss the sequel opening and backlash.",
            published_at=now,
            metadata={"upvotes": 800},
            comments=250,
        )])[0]
        listener = Submission(
            "https://example.com/listener", "Shah Rukh Khan sequel box office debate", "Form",
            "Listeners want the opening and backlash discussed", "Asha", True, False,
            duplicate_count=2,
        )

        enrich_story_intelligence([news, reddit], [listener])

        self.assertEqual(news.source_summary, {"google_news": 3, "reddit": 1, "listener": 2})
        self.assertEqual(news.related_stories[0]["title"], reddit.title)
        self.assertIn("Shared story terms", news.related_stories[0]["relationship"])
        self.assertEqual(news.lifecycle, "Peaking")
        self.assertEqual(len(news.discussion_questions), 3)
        self.assertIn("3 Google News, 1 Reddit, 2 listener", news.confidence_explanation)

    def test_story_lifecycle_covers_breaking_developing_and_fading(self):
        now = datetime.now(timezone.utc)
        breaking = rank_stories([Story(
            "Official trailer released", "https://example.com/breaking", "Google News",
            published_at=now,
        )])[0]
        developing = rank_stories([Story(
            "Casting discussion continues", "https://example.com/developing", "Google News",
        )])[0]
        fading = rank_stories([Story(
            "Old release update", "https://example.com/fading", "Google News",
            published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )])[0]

        enrich_story_intelligence([breaking, developing, fading], [])

        self.assertEqual(breaking.lifecycle, "Breaking")
        self.assertEqual(developing.lifecycle, "Developing")
        self.assertEqual(fading.lifecycle, "Fading")

    def test_substantive_signals_outrank_routine_promotion(self):
        substantive = Story(
            "Franchise sequel faces audience backlash after box office opening",
            "https://example.com/substantive",
            "Google News",
        )
        routine = Story(
            "Official sequel poster photos and BTS images released",
            "https://example.com/routine",
            "Google News",
        )
        ranked = rank_stories([routine, substantive])
        self.assertEqual(ranked[0].title, substantive.title)
        self.assertGreater(substantive.metadata["editorial_signal_adjustment"], routine.metadata["editorial_signal_adjustment"])

    def test_ambiguous_news_terms_get_bollywood_context(self):
        self.assertEqual(_google_news_query("War 2"), '"War 2" Bollywood')
        self.assertEqual(_google_news_query("Bollywood box office"), "Bollywood box office")

    def test_world_war_2_does_not_match_film_watchlist(self):
        story = Story("The best World War 2 films", "https://example.com/world-war", "Google News")
        scored = rank_stories([story], ["War 2"])[0]
        self.assertEqual(scored.metadata["watchlist_matches"], [])

    def test_google_news_relevance_gate_rejects_general_controversy(self):
        general = Story("Exam faces backlash after disputed question", "", "Google News")
        film = Story("Bollywood film faces backlash after casting change", "", "Google News")
        self.assertFalse(_is_bollywood_relevant(general, "Bollywood controversy"))
        self.assertTrue(_is_bollywood_relevant(film, "Bollywood controversy"))

    def test_google_news_rejects_query_label_pages(self):
        generic = Story("Bollywood movie controversy - ScoopWhoop", "", "Google News")
        specific = Story("Actor responds to Bollywood controversy - Example", "", "Google News")
        self.assertTrue(_is_low_information_result(generic, "Bollywood movie controversy"))
        self.assertFalse(_is_low_information_result(specific, "Bollywood controversy"))

    def test_recording_prep_selection_caps_repeated_feeds(self):
        items = [
            Story(f"Box office update {index}", f"https://example.com/{index}", "Google News", metadata={"keyword": "Bollywood box office"})
            for index in range(4)
        ]
        items.append(Story("Casting update", "https://example.com/casting", "Google News", metadata={"keyword": "Bollywood casting"}))
        selected = select_diverse_stories(items, 3, max_per_google_keyword=2)
        self.assertEqual([item.title for item in selected], ["Box office update 0", "Box office update 1", "Casting update"])

    def test_recording_prep_selection_consolidates_same_story_across_queries(self):
        items = [
            Story("Cocktail 2 day 1: Shahid Kapoor sequel opens", "https://example.com/one", "Google News", metadata={"keyword": "Bollywood box office"}),
            Story("Cocktail 2 day 2: Shahid Kapoor film rises", "https://example.com/two", "Google News", metadata={"keyword": "Hindi cinema"}),
            Story("Imtiaz Ali discusses Main Vaapas Aaunga", "https://example.com/three", "Google News", metadata={"keyword": "Bollywood"}),
        ]
        selected = select_diverse_stories(items, 3)
        self.assertEqual([item.title for item in selected], [items[0].title, items[2].title])

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
            "Editorial Note", "Khandaan Take", "Essential Conversations",
            "The Bigger Picture", "From the Khandaan Audience", "Background Reading",
            "Worth discussing", "Why this matters", "Khandaan angle",
            "Discussion prompts", "Supporting evidence", "Editorial Notes",
        ]
        for heading in required:
            self.assertIn(heading, text)
        self.assertNotIn("If We Recorded Tonight", text)
        self.assertNotIn("Discussion 7", text)

    def test_briefing_sorts_by_discussion_score(self):
        lower_priority = Story("High discussion", "", "manual", priority_score=20, discussion_score=90, output_recommendation="Main Episode", khandaan_take="Talk about this.")
        higher_priority = Story("High priority", "", "manual", priority_score=95, discussion_score=40, output_recommendation="Newsletter", khandaan_take="Less to discuss.")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "briefing.md"
            render_briefing(output, [higher_priority, lower_priority], [], [], [], fallback_editorial())
            text = output.read_text(encoding="utf-8")
        shortlist = text.split("## 3. Essential Conversations", 1)[1].split("## 4. The Bigger Picture", 1)[0]
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
            "Essential Conversations", "The Bigger Picture", "From the Khandaan Audience",
            "START HERE", "PATTERNS, NOT PULSES", "THE LISTENER&#x27;S DESK",
            "Essential", "Worth discussing", "editorial-brief", "exports/briefing.md",
            "poster.jpg", "under 1h old", "CONFIRMED SIGNAL", "Copy conversation notes",
            "data-copy-target", "CONVERSATION NOTES", "fallbackCopy", "KHANDAAN", "BOLLYWOOD <em>RADAR</em>",
            "The conversations still worth having <em>after the headlines</em>",
            "A fortnightly editorial briefing on the Bollywood stories, debates and industry shifts still worth discussing.",
            "Bollywood news, Bollywood Reddit, Bollywood gossip, Bollywood box office, Hindi cinema, Bollywood podcast, Khandaan Podcast, Bollywood discussions, Bollywood trends",
            "Khandaan Bollywood Radar is an editorial briefing that turns news, fan discussions, Reddit conversations, X chatter and listener submissions into conversations worth returning to.",
            "Produced by Khandaan: A Bollywood Podcast", "https://www.youtube.com/@KhandaanPodcast",
            "Why this matters", "Khandaan angle", "Discussion prompts", "Supporting evidence",
            "Editorial Notes", "Story lifecycle", "Clustered articles", "Source summary", "Confidence explanation",
        ):
            self.assertIn(value, text)
        for retired in ("CONTENT PLANNING DASHBOARD", "All Ranked Stories", "Stories To Ignore", "If We Recorded Tonight", "Trending Stories", "editorial-meta", "Why Khandaan should care", "Copy Patreon post"):
            self.assertNotIn(retired, text)
        self.assertNotIn("<script src=", text)

    def test_related_articles_render_as_one_conversation_cluster(self):
        stories = [
            Story(
                "Alpha trailer begins the campaign", "https://example.com/alpha-trailer", "Google News",
                discussion_score=90, priority_score=80, output_recommendation="Main Episode",
                topic_category="casting / production", why_khandaan_should_care="A female-led franchise would change YRF's tentpole strategy.",
                khandaan_take="The question is whether the studio is building a character or merely a brand extension.",
                discussion_questions=["What promise does the trailer make?", "Does the franchise framing expand the audience?"],
                metadata={"watchlist_matches": ["release: Alpha (P1)"]},
            ),
            Story(
                "Alpha casting discussion grows", "https://example.com/alpha-cast", "Google News",
                discussion_score=70, priority_score=70, output_recommendation="Newsletter",
                topic_category="casting / production", metadata={"watchlist_matches": ["release: Alpha (P1)"]},
            ),
            Story(
                "Alpha release date confirmed", "https://example.com/alpha-date", "Google News",
                discussion_score=60, priority_score=60, output_recommendation="Newsletter",
                topic_category="release / promotion", metadata={"watchlist_matches": ["release: Alpha (P1)"]},
            ),
        ]
        enrich_story_intelligence(stories, [])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dashboard.html"
            render_dashboard(output, stories, [], [], [])
            text = output.read_text(encoding="utf-8")
        top = text.split('id="start-here"', 1)[1].split('id="bigger-picture"', 1)[0]
        self.assertEqual(top.count('<article class="story-card">'), 1)
        self.assertIn("What is the strategy behind Alpha?", top)
        self.assertIn("Trailer coverage", top)
        self.assertIn("Casting discussion", top)
        self.assertIn("Release-date news", top)
        self.assertIn('<p>Supporting evidence</p><span>3</span>', top)

    def test_essential_conversations_are_capped_at_five(self):
        stories = [
            Story(
                f"Distinct conversation {index}", f"https://example.com/distinct-{index}", "Google News",
                discussion_score=90 - index, priority_score=80 - index,
                output_recommendation="Main Episode", khandaan_take="A distinct editorial angle.",
            )
            for index in range(7)
        ]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dashboard.html"
            render_dashboard(output, stories, [], [], [])
            text = output.read_text(encoding="utf-8")
        top = text.split('id="start-here"', 1)[1].split('id="bigger-picture"', 1)[0]
        self.assertEqual(top.count('<article class="story-card">'), 5)

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

        priorities = text.split('id="start-here"', 1)[1].split('id="bigger-picture"', 1)[0]
        listeners = text.split('id="listener-submissions"', 1)[1].split('</main>', 1)[0]
        self.assertLess(priorities.index("Discussion lead"), priorities.index("Controversy lead"))
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
