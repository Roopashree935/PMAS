# PMAS — Platform

**Pharmacist-led, Multilingual, Offline-first Medication & Adherence Support**

An independent research prototype developed by Kartik H, pharmacist.

## Project Structure

```
pmas-platform/
│
├── index.html              Landing page — hero, problem, features, research, demo CTA
├── about.html              About — origin story, timeline, design principles
├── contact.html            Contact — form and direct contact info
├── privacy.html            Privacy Policy — data handling, DPDP alignment
├── terms.html              Terms of Use — research prototype disclaimer
├── 404.html                Error page
│
├── assets/
│   ├── css/
│   │   ├── style.css       Design tokens, reset, typography, layout, header, footer
│   │   ├── components.css  Buttons, cards, badges, forms, timeline, demo frame
│   │   ├── utilities.css   Spacing, text, display, responsive, accessibility
│   │   └── animations.css  Scroll reveals, float, pulse, gradient shift, counters
│   │
│   ├── js/
│   │   ├── main.js         Page init, smooth scroll, active nav, header scroll, contact form
│   │   ├── navigation.js   Mobile nav toggle, scroll spy, keyboard nav
│   │   ├── theme.js        Dark/light toggle with localStorage persistence
│   │   └── animations.js   Intersection Observer reveals, counter animation, parallax
│   │
│   └── images/
│       ├── profile/
│       ├── projects/
│       ├── icons/
│       ├── favicon/
│       │   └── favicon.png
│       └── og/
│
├── demo/                   PMAS application (live demo)
│   ├── index.html
│   ├── css/
│   │   └── styles.css
│   └── js/
│       ├── i18n.js         Complete 5-language translations (195 keys × 5)
│       ├── db.js           localStorage wrapper, Study ID, adherence data layer
│       ├── adherence.js    Taken/Delayed/Missed tracking + adherence bars
│       ├── reminders.js    In-app toast + browser Notification API
│       ├── export.js       De-identified research export + patient health summary
│       └── app.js          Core logic: consent, tabs, CRUD, dashboard, safety alert
│
├── files/
│
├── robots.txt
├── sitemap.xml
├── manifest.json
└── README.md
```

## Quick Start

1. **Run locally:** Open `index.html` in any modern browser. No build step, no dependencies, no server required.

2. **Try the demo:** Click "Try Demo" in the navigation, or navigate to `demo/index.html` directly.

3. **Deploy:** Upload all files to any static hosting service (GitHub Pages, Netlify, Vercel, etc.). No backend needed.

## PMAS — Key Features

- **Adherence Tracking** — One-tap Taken / Delayed / Missed for each scheduled dose
- **Multilingual** — English, Telugu, Kannada, Tamil, Hindi (all patient-facing text)
- **Offline-First** — All data in browser localStorage by default; optional opt-in cloud sync
- **Safety Escalation** — Recommends professional evaluation, does not diagnose
- **De-identified Export** — Study ID + Study Day instead of raw dates
- **Patient Health Summary** — Printable report, separate from research export
- **Granular Consent** — Six separate acknowledgements
- **Local Reminders** — In-app toast + browser notifications

## Research Context

- **Affiliation:** Independent — no institutional affiliation
- **Conference:** 5th International HEOR Conference, ISPOR India Andhra Pradesh Chapter
- **Direction:** Vernacular communication focus shaped at the ISPOR India HEOR conference
- **Primary Outcome:** Medication adherence rate (app-tracked + MMAS-8 validated)
- **Design Alignment:** DPDP Act 2023 principles (not a compliance certification)

## Tech Stack

- Pure HTML, CSS, JavaScript (no frameworks, no build tools)
- Progressive enhancement with Intersection Observer, Notification API
- PWA-ready (manifest.json included)
- Accessible (skip links, focus-visible, ARIA labels, reduced-motion support)

## Author

**Kartik H** — B.Pharm (RGUHS), independent digital health researcher
Founder, TechStudyHubCore

## License

Research prototype — academic use. Not for clinical deployment.
