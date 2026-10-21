# Changelog

## 3.1.0

### Fixed
- The integration failed to load: `helpers.py` was missing from the
  repository.
- The verse-of-the-day request now uses the documented
  `/v1/verse-of-the-days/{day}` path, falling back to the older
  `verse_of_the_days` form only if the API answers 404.
- Removing the first tracked version no longer hands its entity id to
  another version. Existing sensors are migrated automatically and keep their
  entity ids.
- Picking a language with no Bible versions now says so, instead of
  "Could not connect".
- An App Key that is recognized but not permitted (HTTP 403) now gets its
  own message instead of "Invalid App Key".
- Changing the language under **Configure** now reloads the version list for
  that language.
- The minimum Home Assistant version is now 2024.12.0, which is what the
  options flow actually needs.

### Added
- New `copyright` attribute: the Bible version's copyright notice, which the
  API's license requires to be shown with the text. A version without a
  notice is shown as unavailable rather than without one.
- New `version` attribute with the version's short name (e.g. `NVI`).
- When the App Key stops working, Home Assistant asks for a new one
  (re-authentication) instead of staying unavailable.
- Adding the same App Key twice is refused; add versions to the existing
  entry instead.
- Automated tests and GitHub validation (hassfest, HACS).

### Changed
- Far fewer API calls: the verse of the day is fetched once per entry (not
  once per version), and once today's verse is in, nothing is requested
  until just after midnight. That is 1 + 3 × versions requests per day,
  down from 72 per version.
- The `text`, `html` and `copyright` attributes are no longer written to
  Home Assistant's history database.
- The interface no longer uses the API provider's name.

## 3.0.0

- Renamed the integration domain from `youversion` to `verse_of_the_day`.
