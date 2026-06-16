---
name: write-issue
description: Create a GitHub issue for maps-timeline using the issue template ($ARGUMENTS optional title or context).
---

# Write GitHub Issue

Create a GitHub issue in **adanmauri/maps-timeline**. $ARGUMENTS is optional:
a title hint, bug/feature description, or existing issue number/URL to **update**
(not create).

## When to use

The user wants a **new GitHub issue** filed before or instead of coding.

## Steps

1. **Existing issue?** If $ARGUMENTS is `#42` or an issue URL, fetch with
   `gh issue view` or GitHub MCP and use `gh issue edit` only when the user asked
   to update — do not create a duplicate.

2. **Fill the [issue template](./template)** — especially **Environment** for
   device/scrape/navigation failures. Write to `data/drafts/ISSUE.md` (`data/` is
   gitignored).

3. **Gather environment data** when a phone was involved. Run (or ask the user to
   run) with the device connected:

   ```bash
   adb shell getprop ro.product.manufacturer
   adb shell getprop ro.product.model
   adb shell getprop ro.product.brand
   adb shell getprop ro.build.version.release
   adb shell getprop ro.build.version.sdk
   adb shell wm size
   adb shell wm density
   adb shell getprop ro.build.display.id
   adb shell dumpsys package com.google.android.apps.maps | grep versionName
   ```

   **OEM UI / skin** — infer from manufacturer + build props when possible:
   - Samsung → One UI (`adb shell getprop ro.build.version.oneui` if present)
   - Xiaomi → HyperOS / MIUI
   - Oppo / OnePlus → ColorOS / OxygenOS
   - Google → stock Pixel
   - Motorola, Sony, etc. → note as close as possible; use `TBD` if unknown

   Also note: host OS, `maps-timeline` version, `--prefer u2|adb`, Maps language,
   font/display scale, dark mode, battery saver, cable vs wireless ADB, foldable
   display, work profile — anything that could change the accessibility tree or
   navigation.

4. **Pick a title** — short, action-oriented (from $ARGUMENTS or conversation).

5. **Create the issue**

   ```bash
   mkdir -p data/drafts
   gh issue create \
     --title "<title>" \
     --body-file data/drafts/ISSUE.md \
     --label "<bug|enhancement|documentation>"
   ```

   Or GitHub MCP with the same title and body. Use `--label` only when the label
   exists in the repo.

6. **Return the issue URL** to the user.

## Rules

- Do not commit drafts under `data/` or paste real addresses from Timeline data.
- Scrub place names from XML/screenshots before attaching; describe dumps as
  "anonymized" in the issue.
- Offline `parse-file` bugs: Environment can be shortened (host OS + dump source);
  still note Maps UI language if relevant to selectors.
