# 📖 YouVersion Bible API – Home Assistant Integration (Unofficial)

This is an **unofficial Home Assistant integration** that retrieves the *Verse of the Day* and other Bible information from the **official YouVersion API** and makes it available as a sensor inside Home Assistant.

The integration runs entirely inside your Home Assistant instance and does **not** redistribute, store, or modify any Bible text.

---

## ⚠️ Important Notice

This project:

- **is not affiliated** with YouVersion or Life.Church  
- **does not redistribute** Bible content  
- **does not store** text permanently  
- **does not provide** a public API  
- **uses only** the official YouVersion Developer API  
- **displays content locally** inside Home Assistant  

### Required Attribution  
**Bible text courtesy of YouVersion.**

---

## 🧩 Features

- Fetches the **Verse of the Day** from the official YouVersion API  
- Creates a Home Assistant sensor with:  
  - verse text  
  - reference  
  - Bible version  
- Updates automatically  
- Supports configuration via UI (Config Flow)  
- Works with automations and notifications  

---

## 🛠️ Installation (HACS)

1. Open **HACS → Integrations**  
2. Click the menu (⋮) → **Custom repositories**  
3. Add this repository:

```
https://github.com/gugahdl/Bible-API
```

4. Category: **Integration**  
5. Install the integration  
6. Go to **Settings → Devices & Services → Add Integration**  
7. Search for **YouVersion Bible API**  
8. Enter your **Developer Token**  
9. Choose your **Bible version** and **language** from the dropdowns (fetched live from your YouVersion account)  

You can change the version or language later from the integration's **⚙️ Configure** button, without removing it.

---

## 📊 Sensor state and attributes

The sensor state is the **short reference** (e.g. `John 3:16`), kept under Home Assistant's 255-character state limit. The full verse and related data are exposed as attributes:

| Attribute | Description |
|---|---|
| `text` | Full verse text (falls back to a stripped version of `html` if the API doesn't provide plain text for that version) |
| `html` | Raw HTML verse content, if provided by the API (may be `null`) |
| `reference` | Same short reference as the state |
| `usfms` | USFM verse code(s), e.g. `["JHN.3.16"]` |
| `url` | Link to the verse on bible.com |
| `image_url` / `image_attribution` | Verse-of-the-day background image, if provided |
| `day` | Day of the year (1–366) the verse belongs to |
| `version_id` | The numeric Bible version ID currently selected |

⚠️ If you build a custom dashboard card (e.g. Markdown) that reads an attribute directly with `state_attr(...)`, guard against missing data with a Jinja default, since a `null` attribute renders as the literal text `None`:

```jinja
{{ state_attr('sensor.youversion_verse_of_the_day', 'text') | default('Verse unavailable', true) }}
```

---

## 🔔 Example Automation

```yaml
automation:
  - alias: Verse of the Day Notification
    trigger:
      - platform: time
        at: "08:00:00"
    action:
      - service: notify.mobile_app_my_phone
        data:
          title: "Verse of the Day"
          message: >
            {{ state_attr('sensor.youversion_verse_of_the_day', 'text') | default('Verse unavailable', true) }}
            ({{ states('sensor.youversion_verse_of_the_day') }})
```

---

## 📄 License

This project is licensed under the MIT License.  
Bible content belongs to YouVersion and is used according to their Terms of Use.
