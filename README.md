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
8. Enter your **Developer Token** and preferred Bible version  

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
            {{ states('sensor.youversion_verse_of_the_day') }}
            ({{ state_attr('sensor.youversion_verse_of_the_day', 'reference') }})
```

---

## 📄 License

This project is licensed under the MIT License.  
Bible content belongs to YouVersion and is used according to their Terms of Use.

---

Se quiser, posso gerar também uma versão em português ou uma versão mais completa com badges, imagens e instruções avançadas.
