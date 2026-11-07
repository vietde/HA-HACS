# AquaTrax — Home Assistant custom integration

Reads your water usage from the AquaTrax customer portal
([myaquatrax.com](https://myaquatrax.com)) into Home Assistant.

AquaTrax is the customer portal used by a number of California water
utilities, including the **San José Municipal Water System**. There is no
official Home Assistant integration and no public customer API, so this
integration signs into the portal the same way a browser does and reads
the usage figures off your dashboard.

## What you get

- **Water Total** — cumulative usage in gallons (`total_increasing`, so
  it works in the Energy dashboard's water section)
- **Water Today / This Week / This Month / Billing Period** — gallons

The portal's own data updates about once a day, so the integration
checks every 6 hours by default (changeable in Configure).

## Install

1. In Home Assistant, open **Settings → Marketplace** (HACS).
2. Top-right menu → **Custom repositories** → add this repo's URL,
   category **Integration**.
3. Find **AquaTrax** in the Marketplace and install it.
4. **Restart Home Assistant.**
5. Go to **Settings → Devices & Services → Add Integration → AquaTrax**,
   pick your water district (for San José Municipal Water: **City of
   San Jose**), and enter the email and password you use at
   myaquatrax.com.

## Before you set it up

You need an AquaTrax account first. At myaquatrax.com, click
**Register Now** (you'll need the account number and meter number from
your water bill), or check your email for an auto-registration message
from AquaTrax and use **Forgot Password** to set a password.

## Notes and limits

- This is an unofficial integration, not affiliated with AquaTrax or
  your water utility. It works by signing into the portal's web pages;
  if AquaTrax redesigns the portal it may need an update.
- The portal reports usage in CCF or gallons depending on the utility;
  the integration converts everything to gallons.
- Daily / weekly / monthly figures only appear after the portal's usage
  changes at least once after setup — the first real numbers usually
  show up the morning after the second data pull, just like the
  electric/gas utility meters.
- Do not set the check interval below 6 hours. Utility portals
  rate-limit repeated sign-ins.

## Status

v0.1.0 — built 2026-11-07. The sign-in flow (utility dropdown, form
POST) was verified against the public login page. The dashboard parsing
has not been tested against a real account yet: the first setup will
confirm which usage figures the San Jose dashboard shows, and the
parser will be adjusted if needed.
