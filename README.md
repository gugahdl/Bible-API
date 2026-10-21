<p align="center">
  <img src="https://raw.githubusercontent.com/gugahdl/Bible-API/main/logo.png" width="120" alt="Open book">
</p>

# 📖 Bible Verse of the Day for Home Assistant

A [Home Assistant](https://www.home-assistant.io/) custom integration that
publishes a daily Bible verse as a sensor. It reads from the YouVersion
Platform API (`https://api.youversion.com/v1`) using an App Key you request
yourself, directly from the API provider.

This is an independent project built by a hobbyist for personal,
non-commercial use. It is **not** a product of, and is **not distributed,
reviewed, endorsed, or supported by**, the company behind that API. There is
no partnership, sponsorship, or business relationship of any kind.

---

## What this is (and isn't)

- **Is:** a small piece of code that calls a public developer API and shows
  the result as a Home Assistant sensor. Free, with no ads, paywalls, or
  subscriptions.
- **Is not:** an official app, plugin, or integration of the API provider.
- **Does not** ship or redistribute Bible text: the text is fetched live
  into your own Home Assistant and kept out of its history database.
- **Does not** ship an App Key: every user gets their own. The API's terms
  require keeping the key private, so never post yours in an issue, a
  screenshot, or a log.
- **Copyright:** Bible text belongs to its publishers. Each version's
  copyright notice comes with the sensor (the `copyright` attribute) and
  **must be shown together with the text** — the examples below do that.

If anything in this repository or its documentation ever reads as if it were
an official release, that's a mistake — please open an issue.

---

## Requirements

- Home Assistant **2024.12.0** or newer
- [HACS](https://hacs.xyz/)
- Your own, free **App Key** (see below)

### Getting an App Key

This project has nothing to do with issuing keys; you get yours from the API
provider:

1. Go to <https://developers.youversion.com>, open the Platform Portal and
   sign in with (or create) an account.
2. Register an application — any name works, it's just a label in your own
   developer dashboard — and accept the developer terms.
3. Accept the license of each Bible version you want to use. Only versions
   whose license you accepted can be fetched.
4. Copy the **App Key** shown for that application.

> The old "Developer Token" from the provider's previous, now-retired API
> does not work here. You need an App Key from the current platform.

---

## Installation (HACS)

1. In HACS, open the three‑dot menu → **Custom repositories**.
2. Add `https://github.com/gugahdl/Bible-API` with category **Integration**.
3. Search HACS for **Bible Verse of the Day** and download it.
4. **Restart Home Assistant.**
5. Go to **Settings → Devices & services → Add integration** and search for
   **Bible Verse of the Day**.
6. Paste your **App Key** and pick a **language** (e.g. `por`, `eng`, `spa`).
7. Pick **one or more Bible versions** from the list — only versions enabled
   for your App Key in that language are shown.

Each version you pick becomes its own device with its own sensor (e.g. one
for NVI, one for ARC). Add or remove versions, or change the language, any
time from this integration's **Configure** button — you only enter the App
Key once, at step 6. If the key ever stops working, Home Assistant asks you
to re-authenticate (under **Settings → Devices & services**) and you paste
a new one there.

---

## The sensors

One sensor is created per tracked version, named e.g.
**`sensor.nvi_verse_of_the_day`** or **`sensor.arc_verse_of_the_day`**
(confirm the exact entity ids under *Developer tools → States*).

- **State:** the short reference, e.g. `João 3:16` — kept under Home
  Assistant's 255‑character state limit.

| Attribute | Example | Notes |
|---|---|---|
| `text` | `Porque Deus tanto amou o mundo…` | plain‑text verse in that device's version |
| `html` | `<div>…</div>` | HTML rendering; can be `null` |
| `copyright` | `Nova Versão Internacional © …` | the version's copyright notice — show it with the text |
| `reference` | `João 3:16` | localized to the version's language |
| `passage_id` | `JHN.3.16` | USFM id of the passage |
| `day` | `294` | day of the year (1–366) the verse belongs to |
| `version` | `NVI` | short name of the Bible version |
| `version_id` | `129` | id of that device's Bible version |
| `url` | `https://www.bible.com/bible/129/JHN.3.16` | opens the verse on bible.com |

The `text`, `html` and `copyright` attributes are not saved in Home
Assistant's history; only the reference is.

If the verse can't be fetched for a version — for example because its
license isn't accepted for your App Key — that version's sensor shows as
`unavailable` while the others keep working.

---

## Lovelace — Markdown card

```yaml
type: markdown
content: |
  {% set s = 'sensor.nvi_verse_of_the_day' %}
  ## 📖 Verse of the Day
  {% if state_attr(s, 'text') %}
  > {{ state_attr(s, 'text') }}

  **— {{ state_attr(s, 'reference') }}**  ·  [bible.com]({{ state_attr(s, 'url') }})

  <sub>{{ state_attr(s, 'copyright') }}</sub>
  {% else %}
  _Currently unavailable._
  {% endif %}
```

---

## Automation — daily notification

```yaml
automation:
  - alias: Verse of the Day notification
    trigger:
      - platform: time
        at: "08:00:00"
    condition:
      - condition: template
        value_template: "{{ state_attr('sensor.nvi_verse_of_the_day', 'text') is not none }}"
    action:
      - service: notify.mobile_app_my_phone
        data:
          title: "Verse of the Day — {{ states('sensor.nvi_verse_of_the_day') }}"
          message: >
            {{ state_attr('sensor.nvi_verse_of_the_day', 'text') }}

            {{ state_attr('sensor.nvi_verse_of_the_day', 'copyright') }}
```

---

## Voice assistants and AI

The API's terms do not allow using its content in open-ended AI chat, or to
train AI. If you use an AI-powered conversation agent in Home Assistant
(Assist with an LLM), **don't expose these sensors to it** (*Settings →
Voice assistants → Expose*). Reading the verse out word for word — for
example with a text-to-speech action — is fine.

---

## How often it calls the API

The verse changes once a day, so the integration fetches it right after
midnight and then keeps it: per entry that is **1 request for the day's
verse plus 3 per tracked version** (text, HTML, copyright notice) per day. If
something fails, it retries the missing parts every hour.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| **Invalid App Key** | Wrong key, or an old "Developer Token" from the retired API. Get an App Key at <https://developers.youversion.com>. |
| **The App Key was recognized but is not allowed…** | The app may be archived on the developer portal, or no Bible license is accepted yet. Check the app on the portal. |
| **No Bible versions were returned** | Nothing is enabled for your App Key in that language. Try another code (e.g. the 2‑letter `en`, `pt`, `es`), or accept more Bible licenses on the portal. |
| **This App Key is already configured** | Use the existing entry's **Configure** button to add versions. |
| **One of the selected versions is already tracked…** | Another entry tracks that version. Pick a different one, or edit that other entry. |
| One sensor `unavailable`, others fine | That version's license isn't accepted for your key, or it has no copyright notice to show. Check **Settings → System → Logs** (filter `verse_of_the_day`). |
| All sensors `unavailable` | Usually a temporary API problem or rate limit; it retries every hour. Check the logs. |
| **Could not connect to the Bible API** | Make sure you're on **v3.1.0 or newer** and that Home Assistant has internet access. |

---

## Upgrading

- **From 3.0.x:** just update in HACS and restart. Existing sensors keep
  their entity ids. The new `copyright` attribute appears automatically —
  add it to your cards and notifications.
- **From versions before 3.0.0:** those used the domain `youversion`, which
  was renamed to `verse_of_the_day` so the project isn't identified by the
  API provider's name. Home Assistant treats it as a different integration:
  1. Remove the old entries under **Settings → Devices & services**.
  2. In HACS, remove the custom repository for this project, then add it
     again (same URL).
  3. Restart Home Assistant and add the integration again (App Key +
     versions) — picking the same versions restores the same entity ids.

See [CHANGELOG.md](CHANGELOG.md) for what changed in each release.

---

## Development

```bash
pip install -r requirements_test.txt
pytest
```

---

## License

The code is [MIT](LICENSE). Bible text belongs to its respective publishers
and is used under the license each user accepts with their own App Key.
