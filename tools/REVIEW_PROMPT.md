# Quarterly review instructions

You are checking the photo requirements in `requirements/*.json` against each document's official page.
Accuracy matters more than coverage: people submit these photos to governments. Read `SCHEMA.md` for
what every field means.

For each entry to check (all entries, unless the workflow names specific ids):

1. Open its `source` URL with WebFetch. If the page moved or is gone, look for its replacement **on the
   same government domain** (or the country's official embassy/consulate pages) with WebSearch. Never use
   photo-service companies, blogs, travel agencies or forums as a source.
2. Compare every field in the entry with the page: photo size, head height (and whether it's measured to
   the top of the hair or the skull), eye line, space above the head, face width, background, glasses,
   pixel sizes, upload limit, rules for babies, and whether applicants may still supply their own photo
   (`applicantPhoto`: some countries now take the photo at the office or only accept certified
   photographers).
3. Then, in the JSON file:
   - **Unchanged:** set `verified` to today's date (UTC, YYYY-MM-DD). Change nothing else.
   - **Changed:** edit only the fields that changed, set `verified` to today, and update `source` if the
     page moved. Convert units exactly as SCHEMA.md says (e.g. "70–80% of a 45 mm photo" → [31.5, 36]).
   - **Couldn't read the page** (blocked, 403, down, no replacement found): change nothing, not even
     `verified`.
   - Never guess or fill a value that isn't printed on an official page. If the page is ambiguous, leave
     the value as it is and say so in the evidence note.
4. Record what you found in `review/evidence.json` (overwrite it each run):

```json
{
  "checkedAt": "YYYY-MM-DD",
  "documents": [
    {
      "id": "ca-passport",
      "status": "unchanged | changed | unreachable",
      "source": "https://… the page you actually read",
      "note": "one sentence: what you found, or why it couldn't be checked",
      "changes": [
        {
          "field": "headHeightMM",
          "sourceURL": "https://… the page containing the quote",
          "quote": "the exact words from the page, copied verbatim, at most 300 characters",
          "reasoning": "how the new value follows from the quote, including any unit conversion"
        }
      ]
    }
  ]
}
```

   Every changed field needs its own `changes` record with a verbatim quote. A change without a quote is
   shown to the reviewer as unsupported and should not be made.
5. Finally run `python3 tools/validate.py` and fix any errors it reports in the files you edited.

Don't add or remove documents in this review, don't reformat files, and don't touch anything outside
`requirements/` and `review/evidence.json`.
