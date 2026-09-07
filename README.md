[README.md](https://github.com/user-attachments/files/31894173/README.md)<p align="center">
  <img src="https://raw.githubusercontent.com/gugahdl/Bible-API/main/logo.png" width="120" alt="Open book">
</p>

# 📖 Bible Verse of the Day for Home Assistant

A [Home Assistant](https://www.home-assistant.io/) custom integration that
publishes a daily Bible verse as a sensor. It works by calling the
**YouVersion Platform API** (`https://api.youversion.com/v1`) with an App Key
you request yourself directly from YouVersion.

This is an independent project built by a hobbyist for personal, non-commercial
use. It is **not** a product of, and is **not distributed, reviewed, or
supported by**, the company behind that API.

---

## What this is (and isn't)

- **Is:** a small piece of code that calls a public developer API and shows
  the result as a Home Assistant sensor.
- **Is not:** an official app, plugin, or integration published or endorsed by
  YouVersion / Life.Church. There is no partnership, sponsorship, or business
  relationship of any kind.
- **Does not** redistribute or permanently store Bible text — it is fetched
  live and shown locally in your own Home Assistant instance.
- **Attribution:** *Scripture provided by YouVersion.* Use of the API is
  subject to [YouVersion's Terms of Use](https://platform.youversion.com/?tos=1).

If anything in this repository or its documentation ever reads as if it were
an official release, that's a mistake — please open an issue.

---

## Requirements

- Home Assistant **2024.4.0** or newer
- [HACS](https://hacs.xyz/)
- Your own, free **App Key** for the YouVersion Platform API

### Getting an App Key (from YouVersion directly — this project has nothing to do with issuing it)

1. Go to <https://developers.youversion.com> and sign in with (or create) a
   YouVersion account.
2. Register an application — any name works, it's just a label in your own
   developer dashboard.
3. Copy the **App Key** shown for that application.

> This is unrelated to the old "Developer Token" from YouVersion's previous,
> now-retired API platform. Only an App Key from the current platform works
> here.

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
for NVI, one for ARC). Add or remove versions any time from this
integration's **Configure** button — you only enter the App Key once, at
step 6.

---

## The sensors

One sensor is created per tracked version, named e.g.
**`sensor.nvi_verse_of_the_day`** or **`sensor.arc_verse_of_the_day`**
(confirm the exact entity ids under *Developer tools → States*).

- **State:** the short reference, e.g. `John 3:16` — kept under Home
  Assistant's 255‑character state limit.

| Attribute | Example | Notes |
|---|---|---|
| `text` | `For God so loved the world…` | plain‑text verse in that device's version |
| `html` | `<div>…</div>` | HTML rendering; can be `null` |
| `reference` | `John 3:16` | localized to the version's language |
| `passage_id` | `JHN.3.16` | USFM id of the passage |
| `day` | `240` | day of the year (1–366) the verse belongs to |
| `version_id` | `129` | id of that device's Bible version |
| `url` | `https://www.bible.com/bible/129/JHN.3.16` | opens the verse on bible.com |

> A `null` attribute renders as the literal string `None` in templates. Guard
> it with a Jinja default:
>
> ```jinja
> {{ state_attr('sensor.nvi_verse_of_the_day', 'text') | default('unavailable', true) }}
> ```

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
    action:
      - service: notify.mobile_app_my_phone
        data:
          title: "Verse of the Day"
          message: >
            {{ state_attr('sensor.nvi_verse_of_the_day', 'text') | default('unavailable', true) }}
            ({{ states('sensor.nvi_verse_of_the_day') }})
```

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| **Could not connect to the YouVersion API** | Make sure the integration is on **v2.0.0 or newer** — an earlier, unrelated API host this project used to call no longer exists. Update via HACS and restart. |
| **Invalid YouVersion App Key** | Wrong key, or an old "Developer Token" from the retired API. Get an App Key at <https://developers.youversion.com>. |
| **No Bible versions were returned** | The language code returned nothing for your App Key. Try the 2‑letter form (`en`, `pt`, `es`) in the language field, or enable more Bibles for your app on the developer portal. |
| **This Bible version is already tracked...** | You picked a version another entry already tracks. Pick a different one, or edit that other entry instead. |
| Sensor becomes `unavailable` after working | Usually a transient API error or rate limit; the integration retries automatically and recovers within about an hour. Check **Settings → System → Logs** (filter `verse_of_the_day`). |

---

## Upgrading from an older release of this project

Versions before **3.0.0** used the folder/domain name `youversion` (matching
the API this project talks to, not any product name of ours). That has been
renamed to `verse_of_the_day` so the project isn't identified by that
company's name. Home Assistant treats this as a different integration, so:

1. Remove the old entries under **Settings → Devices & services** (they'll be
   named "YouVersion...").
2. In HACS, remove the custom repository for this project, then add it again
   (same URL) so it picks up the new folder cleanly.
3. Restart Home Assistant.
4. Add the integration again as described above (App Key + versions) —
   picking the same versions you had before restores the same entity ids.

---

## License

[MIT](LICENSE). Bible text belongs to YouVersion and the respective
publishers and is used under YouVersion's Terms of Use.

