---
name: write-issue
description: File a GitHub issue for maps-timeline that follows the repo's issue forms, with the phone details a scrape bug needs. Use when the user wants a bug, feature or docs issue filed (or an existing one updated).
---

# Write GitHub Issue

## Objective

File an issue in `adanmauri/maps-timeline` whose body matches the repo's issue forms, so it reads
the same as one opened from the web.

## Workflow

1. **Existing issue?** If the request names one (`#42` or a URL), read it with `gh issue view`
   and edit it with `gh issue edit` only when the user asked for an update. Never file a
   duplicate; search first: `gh issue list --search "<keywords>"`.
2. **Pick the form** under [`.github/ISSUE_TEMPLATE/`](../../../.github/ISSUE_TEMPLATE/):
   `bug-report.yaml`, `feature-request.yaml` or `documentation.yaml`.
3. **Fill it:** write each field of the form as a `### <label>` heading followed by its answer,
   in the form's order, into the git-ignored scratch file `issue-body.tmp` (matched by `*.tmp`).
   Keep a field's heading with `_No response_` when there is nothing to say.
4. **Phone details** for a bug on the phone. These read-only commands fill the "Phone and Google
   Maps" field; run them, or ask the user to, with the phone connected:

   ```bash
   adb shell getprop ro.product.manufacturer
   adb shell getprop ro.product.model
   adb shell getprop ro.build.version.release
   adb shell getprop ro.build.version.sdk
   adb shell wm size
   adb shell wm density
   adb shell dumpsys package com.google.android.apps.maps | grep versionName
   ```

   Infer the OEM UI from the manufacturer (Samsung: One UI; Google: stock Pixel; Xiaomi: HyperOS
   or MIUI); write `unknown` rather than guess. Never include the device serial.
5. **Title:** short and specific, without the `(short issue description)` placeholder.
6. **Create it** with the form's label:

   ```bash
   gh issue create --title "<title>" --body-file issue-body.tmp --label <bug|enhancement|documentation>
   ```

7. Return the issue URL.

## Rules

- No real location data: no place names, addresses, coordinates or dates of real visits. A dump
  or screenshot is anonymized before it is attached, and the issue says so (see the
  [scraper guardrails](../../rules/scraper-guardrails.md)).
- A bug that needs no phone (`normalize`, `import`, `stats`, `parse-file`) can skip the phone
  details, but still names the command and the version.
- No tool attribution in the title or body (see `create-commit`).
