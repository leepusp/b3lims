"""Advanced search of the Notebook dashboard."""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models.lab_tools.notebook import NotebookEntry
from core.models.lab_tools.notebook_collab import NotebookComment
from core.models import Tag
from core.models.lab_tools.notebook_composer import NotebookStep
from core.services.notebook_search import SearchSyntaxError, build_query, has_structured_syntax


@override_settings(FORCE_SCRIPT_NAME=None)
class SearchBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.ana = User.objects.create_user("ana", first_name="Ana", last_name="Lima", password="x")
        cls.bob = User.objects.create_user("bob", password="x")

        def make(title, **kw):
            kw.setdefault("author", cls.ana)
            kw.setdefault("visibility", "lab")
            return NotebookEntry.objects.create(title=title, **kw)

        cls.gel = make("Gel run 1", status="completed", content="<p>agarose 1%</p>", rating=4,
                       experiment_date=date(2026, 2, 10),
                       metadata={"extra_fields": {"Medium": {"type": "text", "value": "TSB broth"}}})
        cls.pcr = make("PCR of 16S", status="draft", entry_type="protocol", rating=2,
                       experiment_date=date(2026, 5, 1),
                       metadata={"extra_fields": {"Medium": {"type": "text", "value": "LB"}}})
        cls.bobs = make("Bob gel", author=cls.bob, status="completed", rating=5)
        cls.blank = make("Nothing here", status="reviewed")

        pcr_tag, _ = Tag.objects.get_or_create(name="pcr")
        cloning, _ = Tag.objects.get_or_create(name="cloning")
        cls.pcr.shared_tags.add(pcr_tag)
        cls.gel.shared_tags.add(cloning)
        cls.gel.shared_tags.add(pcr_tag)
        NotebookStep.objects.create(entry=cls.pcr, body="Centrifuge 5 min")
        NotebookComment.objects.create(entry=cls.gel, author=cls.bob, body="looks clean")

    def titles(self, query, user=None):
        qs = NotebookEntry.objects.filter(build_query(query, user or self.ana)[0]).distinct()
        return sorted(qs.values_list("title", flat=True))


class ParserTests(SearchBase):
    def test_plain_words_are_not_structured(self):
        self.assertFalse(has_structured_syntax("gel electrophoresis"))
        self.assertFalse(has_structured_syntax("16S: PCR"))  # unknown field name stays text
        self.assertTrue(has_structured_syntax("title:gel"))
        self.assertTrue(has_structured_syntax("a or b"))
        self.assertTrue(has_structured_syntax("-draft"))

    def test_plain_query_keeps_legacy_substring_behaviour(self):
        self.assertEqual(self.titles("Gel run"), ["Gel run 1"])
        self.assertEqual(self.titles("#" + str(self.pcr.pk)), ["PCR of 16S"])

    def test_field_and_combination(self):
        self.assertEqual(self.titles("title:gel and status:completed"), ["Bob gel", "Gel run 1"])
        self.assertEqual(self.titles("title:gel status:completed author:bob"), ["Bob gel"])

    def test_or_and_precedence(self):
        # AND binds tighter than OR
        self.assertEqual(
            self.titles("status:draft or title:gel and author:bob"), ["Bob gel", "PCR of 16S"]
        )
        self.assertEqual(
            self.titles("(status:draft or title:gel) and author:bob"), ["Bob gel"]
        )

    def test_negation_forms_agree(self):
        dash = self.titles("title:gel -author:bob")
        word = self.titles("title:gel not author:bob")
        self.assertEqual(dash, ["Gel run 1"])
        self.assertEqual(dash, word)

    def test_negated_tag_excludes_entries_with_it(self):
        self.assertEqual(self.titles("-tag:pcr title:gel"), ["Bob gel"])

    def test_tag_and_hash(self):
        self.assertEqual(self.titles("tag:#cloning"), ["Gel run 1"])
        self.assertEqual(self.titles("tag:pcr"), ["Gel run 1", "PCR of 16S"])

    def test_choice_values_validated_and_label_accepted(self):
        self.assertEqual(self.titles("type:protocol"), ["PCR of 16S"])
        self.assertEqual(self.titles("status:in-progress"), [])
        with self.assertRaisesMessage(SearchSyntaxError, "Valid values"):
            build_query("status:finished")

    def test_rating_comparisons(self):
        self.assertEqual(self.titles("rating>=4"), ["Bob gel", "Gel run 1"])
        self.assertEqual(self.titles("rating<3 rating>0"), ["PCR of 16S"])
        with self.assertRaises(SearchSyntaxError):
            build_query("rating:abc")

    def test_dates(self):
        self.assertEqual(self.titles("date>=2026-03-01"), ["PCR of 16S"])
        self.assertEqual(self.titles("date:2026-02-10"), ["Gel run 1"])
        self.assertEqual(self.titles("created:" + date.today().isoformat()),
                         sorted(NotebookEntry.objects.values_list("title", flat=True)))
        self.assertEqual(self.titles("created<2000-01-01"), [])
        with self.assertRaisesMessage(SearchSyntaxError, "YYYY-MM-DD"):
            build_query("date>=yesterday")

    def test_has_and_related_text(self):
        self.assertEqual(self.titles("has:comments"), ["Gel run 1"])
        self.assertEqual(self.titles("has:steps"), ["PCR of 16S"])
        self.assertEqual(self.titles("step:centrifuge"), ["PCR of 16S"])
        self.assertEqual(self.titles("comment:clean"), ["Gel run 1"])
        self.assertEqual(self.titles("has:files"), [])

    def test_extrafield(self):
        self.assertEqual(self.titles("extrafield:Medium:TSB"), ["Gel run 1"])
        self.assertEqual(self.titles("extrafield:Medium:LB"), ["PCR of 16S"])
        self.assertEqual(self.titles("extrafield:Medium"), ["Gel run 1", "PCR of 16S"])
        self.assertEqual(self.titles("extrafield:Medium:=LB"), ["PCR of 16S"])
        self.assertEqual(self.titles("extrafield:Medium:LB or extrafield:Medium:TSB title:gel"),
                         ["Gel run 1", "PCR of 16S"])
        self.assertEqual(self.titles("extrafield:Nope:x"), [])
        with self.assertRaises(SearchSyntaxError):
            build_query("extrafield:")

    def test_quoted_phrases(self):
        self.assertEqual(self.titles('title:"Gel run"'), ["Gel run 1"])
        self.assertEqual(self.titles('"Bob gel" or title:pcr'), ["Bob gel", "PCR of 16S"])

    def test_author_me(self):
        self.assertEqual(self.titles("author:me title:gel", user=self.bob), ["Bob gel"])
        self.assertEqual(self.titles("author:Lima"), ["Gel run 1", "Nothing here", "PCR of 16S"])

    def test_syntax_errors(self):
        for bad in ("(title:a", "title:a)", "title:a and", 'title:"open', "or title:a"):
            with self.subTest(bad=bad):
                with self.assertRaises(SearchSyntaxError):
                    build_query(bad)

    def test_django_internals_cannot_be_reached(self):
        with self.assertRaises(SearchSyntaxError):
            build_query("extrafield:a__b:x")
        # An unknown "field" is just free text, never a lookup path.
        self.assertEqual(self.titles("author__password:x"), [])


class DashboardSearchTests(SearchBase):
    def setUp(self):
        self.client.force_login(self.ana)

    def get(self, query):
        return self.client.get(reverse("notebook_dashboard"), {"q": query})

    def test_structured_query_filters_rows(self):
        response = self.get("title:gel and author:bob")
        titles = [e.title for e in response.context["page"].object_list]
        self.assertEqual(titles, ["Bob gel"])
        self.assertTrue(response.context["filters"]["q_structured"])

    def test_syntax_error_shows_message_and_no_rows(self):
        response = self.get("(title:gel")
        self.assertEqual(list(response.context["page"].object_list), [])
        self.assertContains(response, 'id="eln-q-error"')
        self.assertContains(response, "Missing")

    def test_private_entries_of_others_never_match(self):
        NotebookEntry.objects.create(title="Secret gel", author=self.bob, visibility="private")
        titles = [e.title for e in self.get("title:gel").context["page"].object_list]
        self.assertNotIn("Secret gel", titles)
        self.assertIn("Bob gel", titles)

    def test_trash_state_still_combines_with_query(self):
        from django.utils import timezone

        self.gel.deleted_at = timezone.now()
        self.gel.deleted_by = self.ana
        self.gel.save()
        response = self.client.get(reverse("notebook_dashboard"), {"q": "title:gel", "state": "trash"})
        self.assertEqual([e.title for e in response.context["page"].object_list], ["Gel run 1"])
        response = self.get("title:gel")
        self.assertNotIn("Gel run 1", [e.title for e in response.context["page"].object_list])

    def test_help_is_rendered(self):
        self.assertContains(self.get(""), "extrafield:Medium:TSB")
