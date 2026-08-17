"""Lead listing, filtering and the saved-leads workflow (spec §14, §17, §57)."""

from tests.conftest import run_search


def first_lead(client, **params) -> dict:
    return client.get("/leads", params=params).json()["items"][0]


# ------------------------------------------------------------------ filtering


def test_min_score_filter(client):
    body = client.get("/leads", params={"min_score": 90}).json()

    assert body["items"]
    assert all(lead["score"] >= 90 for lead in body["items"])


def test_country_filter(client):
    body = client.get("/leads", params={"country": "Spain"}).json()

    assert body["items"]
    assert all(lead["location"]["country"] == "Spain" for lead in body["items"])


def test_repeated_parameters_are_an_or(client):
    body = client.get("/leads", params=[("country", "Spain"), ("country", "Italy")]).json()

    countries = {lead["location"]["country"] for lead in body["items"]}
    assert countries == {"Spain", "Italy"}


def test_platform_filter(client):
    body = client.get("/leads", params={"platform": "linkedin"}).json()

    assert body["items"]
    assert all(
        any(entry["platform"] == "linkedin" for entry in lead["platforms"])
        for lead in body["items"]
    )


def test_signal_filters_are_combined_with_and(client):
    body = client.get("/leads", params=[("signal", "mlm"), ("signal", "leadership")]).json()

    for lead in body["items"]:
        detected = {signal["type"] for signal in lead["signals"] if signal["detected"]}
        assert {"mlm", "leadership"} <= detected


def test_has_email_and_has_social_filters(client):
    with_email = client.get("/leads", params={"has_email": True}).json()
    assert with_email["items"]
    assert all(lead["contacts"].get("email") for lead in with_email["items"])

    social = client.get("/leads", params={"has_social": True}).json()
    assert all(
        any(
            entry["platform"] in {"instagram", "linkedin", "facebook", "threads"}
            for entry in lead["platforms"]
        )
        for lead in social["items"]
    )


def test_free_text_search_matches_name_and_summary(client):
    target = first_lead(client)

    body = client.get("/leads", params={"q": target["name"].split(" ")[0]}).json()

    assert target["id"] in {lead["id"] for lead in body["items"]}


def test_sorting(client):
    by_score = client.get("/leads", params={"sort": "score_desc"}).json()["items"]
    by_name = client.get("/leads", params={"sort": "name_asc"}).json()["items"]

    assert [lead["score"] for lead in by_score] == sorted(
        (lead["score"] for lead in by_score), reverse=True
    )
    assert [lead["name"].lower() for lead in by_name] == sorted(
        lead["name"].lower() for lead in by_name
    )


def test_the_page_size_the_leads_screen_asks_for_is_accepted(client):
    """`/leads/page.tsx` requests 500 in one call — the cap must not reject it."""
    response = client.get("/leads", params={"page_size": 500})

    assert response.status_code == 200
    assert client.get("/leads", params={"page_size": 501}).status_code == 422


def test_pagination_walks_the_whole_set_without_overlap(client):
    first = client.get("/leads", params={"page": 1, "page_size": 4}).json()
    second = client.get("/leads", params={"page": 2, "page_size": 4}).json()

    assert first["total"] == second["total"]
    assert len(first["items"]) == len(second["items"]) == 4
    assert not {lead["id"] for lead in first["items"]} & {lead["id"] for lead in second["items"]}


# ------------------------------------------------------------------ workflow


def test_saving_and_unsaving(client):
    lead = first_lead(client)

    saved = client.post(f"/leads/{lead['id']}/save").json()
    assert saved["saved"] is True
    assert client.get("/leads", params={"saved": True}).json()["items"]

    unsaved = client.delete(f"/leads/{lead['id']}/save").json()
    assert unsaved["saved"] is False


def test_patch_updates_status_and_stamps_updated_at(client):
    lead = first_lead(client)

    updated = client.patch(f"/leads/{lead['id']}", json={"status": "qualified"}).json()

    assert updated["status"] == "qualified"
    assert updated["updatedAt"]
    assert client.get(f"/leads/{lead['id']}").json()["status"] == "qualified"


def test_archived_leads_are_hidden_unless_asked_for(client):
    lead = first_lead(client)
    client.patch(f"/leads/{lead['id']}", json={"archived": True})

    visible = {entry["id"] for entry in client.get("/leads").json()["items"]}
    included = {
        entry["id"]
        for entry in client.get("/leads", params={"include_archived": True}).json()["items"]
    }

    assert lead["id"] not in visible
    assert lead["id"] in included


def test_notes_are_appended_in_order(client):
    lead = first_lead(client)

    client.post(f"/leads/{lead['id']}/notes", json={"body": "Called, no answer"})
    after = client.post(f"/leads/{lead['id']}/notes", json={"body": "Follow up Monday"}).json()

    assert [note["body"] for note in after["notes"]][-2:] == [
        "Called, no answer",
        "Follow up Monday",
    ]
    assert all(note["author"] == "You" for note in after["notes"][-2:])


def test_empty_note_is_rejected(client):
    lead = first_lead(client)

    assert client.post(f"/leads/{lead['id']}/notes", json={"body": ""}).status_code == 422


def test_outreach_draft_uses_the_lead_and_the_chosen_tone(client):
    lead = first_lead(client)

    email = client.post(
        f"/leads/{lead['id']}/outreach",
        json={"channel": "email", "tone": "formal", "language": "Spanish"},
    ).json()
    dm = client.post(
        f"/leads/{lead['id']}/outreach",
        json={"channel": "instagram_dm", "tone": "warm", "language": "Spanish"},
    ).json()

    first_name = lead["name"].split(" ")[0]
    assert email["subject"] and first_name in email["subject"]
    assert email["body"].startswith(f"Dear {first_name}")
    assert dm.get("subject") is None  # a DM has no subject line
    assert first_name in dm["body"]
    assert dm["leadId"] == lead["id"]


def test_facets_come_from_the_data(client):
    body = client.get("/leads/facets").json()

    assert "Spain" in body["countries"]
    assert body["countries"] == sorted(body["countries"])
    assert set(body["platforms"]) <= {
        "instagram",
        "linkedin",
        "facebook",
        "threads",
        "website",
        "blog",
    }


def test_new_search_leads_join_the_shared_lead_list(client):
    before = client.get("/leads").json()["total"]

    search = run_search(client, name="Adds leads")

    after = client.get("/leads").json()["total"]
    assert after == before + search["leadCount"]
