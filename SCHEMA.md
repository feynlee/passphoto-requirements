# Requirement files

These files drive the PassPhoto app. The app downloads them (see `manifest.json`) and falls back to the copy bundled with it.

Each `*.json` file in this folder is an array of specs. The app loads every file and sorts by country.

```jsonc
{
  "id": "us-passport",              // lowercase ISO 3166-1 alpha-2 + "-" + document slug; unique across all files
  "countryCode": "US",              // ISO 3166-1 alpha-2; "EU" for Schengen/EU-wide, "XX" for generic standards
  "country": "United States",       // English short name
  "document": "Passport",           // English, title case: "Passport", "Visa", "ID Card", "Passport Card", "Residence Permit", "Driver's License"
  "kind": "passport",               // passport | visa | id | residence | license | other
  "widthMM": 50.8,
  "heightMM": 50.8,
  "sizeLabel": "2 × 2 in",          // how the issuer writes the size, with ×
  "headHeightMM": [25.4, 34.9],     // chin to top of head INCLUDING hair, [min, max]
  "headTop": "crown",               // optional: only when the issuer measures to the top of the skull, not the hair
  "eyeLineFromBottomMM": [28.6, 34.9], // or null
  "topMarginMM": null,              // top of hair to top edge, or null
  "faceWidthMM": null,              // cheek to cheek, or null
  "background": "whiteOrOffWhite",  // white | whiteOrOffWhite | creamOrLightGrey | lightGrey | plainLight | lightNotWhite | lightBlue | blue | red
  "backgroundFill": "#FFFFFF",      // colour used when the app replaces a background
  "glasses": "notAllowed",          // notAllowed | discouraged | allowed
  "digitalPixels": null,            // [w, h] when the issuer requires an exact digital size
  "minPixels": [600, 600],          // [w, h] minimum for digital submission, or null
  "maxFileKB": null,                // digital upload size cap, or null
  "notes": ["Taken in the last 6 months."],
  "infant": null,                   // only when the issuer states different rules for babies (see below)
  "source": "https://travel.state.gov/…", // the official page the values came from
  "verified": "2026-09-25",         // date the values were checked against the source
  "confidence": "confirmed",
  "applicantPhoto": "accepted",     // optional: accepted (default) | certifiedPhotographerOnly | officeOnly
  "schema": 1                       // optional: the schema version this entry needs; apps skip entries newer than they understand         // confirmed: every number read from the official source; partial: size confirmed, some ranges from a secondary source
}
```

`infant`, when present:

```jsonc
{
  "maxAgeMonths": 12,               // up to which age the infant rules apply, or null if the issuer doesn't say
  "eyesMayBeClosed": true,
  "mouthMayBeOpen": true,
  "headHeightMM": [22, 36],         // only if the issuer gives a different range, else null
  "notes": ["A parent's hand may not be visible."]
}
```
