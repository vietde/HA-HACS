"""Async client for the AquaTrax customer portal (myaquatrax.com).

The portal is a server-rendered ASP.NET MVC site with no public REST API,
so this client reproduces what a browser does: fetch the login page, pick
the water utility from its dropdown, and POST the sign-in form. Usage
figures do NOT come from the dashboard page HTML (it is a JavaScript app)
— they come from the portal's own JSON endpoints, found in its public JS
bundles: /DashboardCustom/GetDashboardDetails (period + latest-day usage),
/Usage/GetHeaderUsage (usage so far this period), /Usage/GetWaterUsage
(daily series, for today / this week / this month). All values are in the
utility's billing unit (CCF for San Jose) and are converted to gallons.

Nothing here is tested against a real account yet (no account existed at
build time); the v0.1.4 endpoint mapping is derived from the portal's own
JS (which fields the dashboard reads). Parsing stays defensive: unknown
shapes yield ``None`` figures instead of exceptions.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from html.parser import HTMLParser
from typing import Any

from aiohttp import ClientSession

from .const import (
    BASE_URL,
    CCF_TO_GAL,
    DASHBOARD_DETAILS_PATH,
    FORM_EMAIL,
    FORM_PASSWORD,
    FORM_REMEMBER_ME,
    FORM_TOKEN,
    FORM_UTILITY,
    HEADER_USAGE_PATH,
    LOGIN_PATH,
    UTILITY_LIST_PATH,
    WATER_USAGE_PATH,
)

_LOGGER = logging.getLogger(__name__)


class AquaTraxAuthError(Exception):
    """Raised when the portal rejects the credentials."""


class AquaTraxConnectionError(Exception):
    """Raised when the portal cannot be reached or returns something unexpected."""


class _FormParser(HTMLParser):
    """Collects <form> actions, <input> fields and <select> options."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[dict[str, Any]] = []
        self._form: dict[str, Any] | None = None
        self._select_name: str | None = None
        self._option_value: str | None = None
        self._option_text: list[str] = []
        self.text_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = dict(attrs)
        if tag == "form":
            self._form = {
                "action": ad.get("action", ""),
                "method": (ad.get("method") or "get").lower(),
                "inputs": {},
            }
            self.forms.append(self._form)
        elif tag == "input" and self._form is not None:
            name = ad.get("name")
            if name:
                self._form["inputs"][name] = {
                    "type": ad.get("type", "text"),
                    "value": ad.get("value", ""),
                    "id": ad.get("id", ""),
                    "placeholder": ad.get("placeholder", ""),
                }
        elif tag == "select":
            self._select_name = ad.get("name") or ad.get("id")
        elif tag == "option" and self._select_name is not None:
            self._option_value = ad.get("value")
            self._option_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._form = None
        elif tag == "select":
            self._select_name = None
        elif tag == "option" and self._select_name is not None:
            text = "".join(self._option_text).strip()
            if self._form is not None and text:
                self._form.setdefault("selects", {}).setdefault(
                    self._select_name, []
                ).append((self._option_value, text))
            self._option_value = None
            self._option_text = []

    def handle_data(self, data: str) -> None:
        if self._option_value is not None:
            self._option_text.append(data)
        if data.strip():
            self.text_chunks.append(data.strip())


def _parse_forms(html: str) -> _FormParser:
    parser = _FormParser()
    parser.feed(html)
    return parser


_NUMBER_RE = re.compile(
    r"(?P<num>[\d,]+(?:\.\d+)?)\s*(?P<unit>CCF|HCF|gallons?|gal|ft3|ft³|m3|m³|liters?|L)\b",
    re.IGNORECASE,
)


def _to_gallons(value: float, unit: str) -> float:
    unit = unit.lower()
    if unit in ("ccf", "hcf"):
        return value * CCF_TO_GAL
    if unit in ("gal", "gallon", "gallons"):
        return value
    if unit in ("ft3", "ft³"):
        return value * 7.48052
    if unit in ("m3", "m³"):
        return value * 264.172
    if unit in ("l", "liter", "liters"):
        return value * 0.264172
    return value


def parse_usage_text(text: str) -> dict[str, float | str | None]:
    """Best-effort extraction of usage figures from dashboard text.

    Looks for numbers near the labels the portal uses (Today / This Week /
    This Month / Billing Period / Current / Meter Read / Total). Returns
    gallons for every figure found, plus the raw unit seen.
    """
    flat = re.sub(r"\s+", " ", text)
    found: dict[str, float | str | None] = {
        "today_gal": None,
        "week_gal": None,
        "month_gal": None,
        "period_gal": None,
        "meter_read_gal": None,
        "unit": None,
    }
    labels = {
        "today_gal": r"today",
        "week_gal": r"(this\s+week|week\s+to\s+date)",
        "month_gal": r"(this\s+month|month\s+to\s+date)",
        "period_gal": r"(billing\s+period|current\s+bill|this\s+billing)",
        "meter_read_gal": r"(meter\s+read|current\s+read|total\s+usage)",
    }
    for key, label in labels.items():
        # Number shortly after the label, or shortly before it.
        for pattern in (
            rf"{label}[^0-9]{{0,80}}?{_NUMBER_RE.pattern}",
            rf"{_NUMBER_RE.pattern}[^A-Za-z]{{0,40}}?{label}",
        ):
            match = re.search(pattern, flat, re.IGNORECASE)
            if match:
                groups = match.groupdict()
                try:
                    value = float(groups["num"].replace(",", ""))
                except (TypeError, ValueError):
                    continue
                unit = groups.get("unit") or ""
                found[key] = _to_gallons(value, unit)
                if unit:
                    found["unit"] = unit
                break
    return found


def _portal_json(text: str) -> dict:
    """Decode a portal JSON response (plain or double-encoded)."""
    data: Any = json.loads(text)
    if isinstance(data, str):
        data = json.loads(data)
    return data if isinstance(data, dict) else {}


def _num(value: Any) -> float | None:
    """Coerce a portal value to float, or None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").strip())
        except ValueError:
            return None
    return None


def _gal_factor(unit_text: str | None) -> float:
    """Gallons per portal unit, from the unit label the portal reports."""
    text = (unit_text or "").lower()
    if "ccf" in text or "hcf" in text:
        return CCF_TO_GAL
    if "m3" in text or "m³" in text or "cubic meter" in text:
        return 264.172
    if "ft3" in text or "ft³" in text or "cubic foot" in text or "cubic feet" in text:
        return 7.48052
    if "liter" in text or text.strip() in ("l",):
        return 0.264172
    return 1.0  # gallons already


def _parse_portal_date(value: Any) -> date | None:
    """Parse a portal date (MM/DD/YYYY, YYYY-MM-DD, or 'Nov 7, 2026')."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y/%m/%d", "%b %d, %Y", "%B %d, %Y"):
        try:
            from datetime import datetime

            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


class AquaTraxClient:
    """Minimal async client for the AquaTrax portal."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session
        self._logged_in = False

    async def fetch_utilities(self) -> dict[str, str]:
        """Return {utility display name: numeric id}.

        The dropdown on the login page is empty in the raw HTML — JavaScript
        fills it from /common/GetMasterUtilityList, so that endpoint is the
        source of truth. Its response is double-encoded JSON:
        {"Results": {"Table": [{"UtilityId": 28, "Name": "City of San
        Jose", ...}]}}. Falls back to parsing <option> elements from the
        login page HTML if the endpoint changes shape.
        """
        try:
            async with self._session.get(BASE_URL + UTILITY_LIST_PATH) as resp:
                raw = await resp.text()
            data: Any = json.loads(raw)
            if isinstance(data, str):
                data = json.loads(data)
            rows = data["Results"]["Table"]
            found = {
                str(row["Name"]): str(row["UtilityId"])
                for row in rows
                if row.get("Name") and row.get("UtilityId") is not None
            }
            if found:
                return found
        except Exception as err:  # noqa: BLE001 - fall through to HTML parsing
            _LOGGER.debug("Utility-list endpoint failed (%s); trying HTML", err)
        try:
            async with self._session.get(BASE_URL + LOGIN_PATH) as resp:
                html = await resp.text()
        except Exception as err:
            raise AquaTraxConnectionError(f"Could not load login page: {err}") from err
        parser = _parse_forms(html)
        for form in parser.forms:
            for name, options in (form.get("selects") or {}).items():
                if "util" in name.lower() or "district" in name.lower() or "agency" in name.lower():
                    return {text: value for value, text in options if value}
        # Fallback: any select with many options is probably the utility list.
        for form in parser.forms:
            for options in (form.get("selects") or {}).values():
                if len(options) >= 5:
                    return {text: value for value, text in options if value}
        return {}

    async def _already_signed_in(self) -> bool:
        """Check whether the shared session is already authenticated.

        GETs the portal home page: an authenticated session lands on the
        dashboard (or a page with account links), an anonymous one is sent
        back to /Account/Login.
        """
        try:
            async with self._session.get(BASE_URL + "/") as resp:
                if "/account/login" in str(resp.url).lower():
                    return False
                text = await resp.text()
        except Exception:  # noqa: BLE001 - not signed in (or unreachable)
            return False
        lowered = text.lower()
        return any(
            marker in lowered
            for marker in ("sign out", "log out", "logout", "my account", "dashboard")
        )

    async def login(self, utility_id: str, email: str, password: str) -> bool:
        """Sign in with the portal form. Returns True on success.

        The sign-in is idempotent: Home Assistant's shared session may
        already be authenticated (the config flow just signed in on the same
        session), in which case the portal redirects an authenticated GET of
        /Account/Login to the dashboard — a page with no sign-in form. That
        is a successful sign-in, not an error (the old code raised "No
        sign-in form found" here and setup retried forever — seen 2026-11-07).
        """
        try:
            async with self._session.get(BASE_URL + LOGIN_PATH) as resp:
                html = await resp.text()
                final_url = str(resp.url)
        except Exception as err:
            raise AquaTraxConnectionError(f"Could not load login page: {err}") from err

        # Already signed in: the portal sent us somewhere other than the
        # login page (typically the dashboard).
        if "/account/login" not in final_url.lower():
            self._logged_in = True
            self._dashboard_url = final_url
            return True

        parser = _parse_forms(html)
        login_form = None
        for form in parser.forms:
            action = (form.get("action") or "").lower()
            if action.rstrip("/").endswith("/account/login") or FORM_EMAIL in form.get("inputs", {}):
                login_form = form
                break
        if login_form is None:
            # No sign-in form on the login page. The session may already be
            # authenticated with the dashboard served without a redirect;
            # probe the home page before giving up.
            if await self._already_signed_in():
                self._logged_in = True
                self._dashboard_url = BASE_URL + "/"
                return True
            if parser.forms:
                login_form = parser.forms[0]
            else:
                raise AquaTraxConnectionError("No sign-in form found on the login page")

        # Preserve the form's own hidden fields verbatim (anti-forgery
        # token, Mfe, IsRegistration, IsSSOEnabled, InvoiceCoudstatus).
        # The server validates them; hardcoding them broke sign-in before
        # (IsRegistration must stay "False" on a login post).
        data: dict[str, str] = {}
        inputs = login_form.get("inputs", {})
        for name, field in inputs.items():
            if field["type"] == "hidden" and name not in data:
                data[name] = field["value"]
        if FORM_TOKEN in inputs:
            data[FORM_TOKEN] = inputs[FORM_TOKEN]["value"]
        # Only these four are ours to set.
        data[FORM_UTILITY] = utility_id
        data[FORM_EMAIL] = email
        data[FORM_PASSWORD] = password
        data[FORM_REMEMBER_ME] = "true"

        action = login_form.get("action") or LOGIN_PATH
        post_url = action if action.startswith("http") else BASE_URL + action
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Origin": BASE_URL,
            "Referer": BASE_URL + LOGIN_PATH,
        }
        try:
            async with self._session.post(
                post_url, data=data, headers=headers, allow_redirects=True
            ) as resp:
                body = await resp.text()
                final_url = str(resp.url)
        except Exception as err:
            raise AquaTraxConnectionError(f"Sign-in request failed: {err}") from err

        if "login" in final_url.lower() and (
            "required" in body.lower() or "invalid" in body.lower() or "incorrect" in body.lower()
        ):
            raise AquaTraxAuthError("Email or password was rejected by AquaTrax")
        if final_url.rstrip("/").lower().endswith("login") or "/account/login" in final_url.lower():
            # Still on the login page with no clear error text: treat as
            # failed auth rather than silently continuing.
            raise AquaTraxAuthError("Sign-in did not leave the login page")
        self._logged_in = True
        self._dashboard_url = final_url
        return True

    async def fetch_usage(self) -> dict[str, float | str | None]:
        """Fetch usage figures (gallons) from the portal's JSON endpoints.

        The dashboard page itself carries no numbers (JavaScript app), so
        this calls the same endpoints the dashboard's own JavaScript calls:
        GetDashboardDetails (period usage, latest-day usage, unit label),
        GetHeaderUsage (usage so far this period), and GetWaterUsage with a
        daily series for the current month (today / this week / this month).
        Values are in the utility's billing unit (CCF for San Jose) and are
        converted to gallons. Falls back to scraping the dashboard page
        text if the endpoints return nothing usable.
        """
        result: dict[str, float | str | None] = {
            "today_gal": None,
            "week_gal": None,
            "month_gal": None,
            "period_gal": None,
            "meter_read_gal": None,
            "unit": None,
            "usage_date": None,
            "billing_period": None,
        }
        result["dashboard_url"] = getattr(
            self, "_dashboard_url", BASE_URL + DASHBOARD_DETAILS_PATH
        )
        try:
            await self._fetch_dashboard_details(result)
            await self._fetch_header_usage(result)
            await self._fetch_daily_series(result)
        except Exception as err:  # noqa: BLE001 - fall back to HTML scraping
            _LOGGER.debug("AquaTrax JSON endpoints failed (%s); trying HTML", err)
        if result["today_gal"] is None and result["period_gal"] is None:
            try:
                html_result = await self._fetch_usage_html()
                for key in ("today_gal", "week_gal", "month_gal", "period_gal", "meter_read_gal"):
                    if result[key] is None and html_result.get(key) is not None:
                        result[key] = html_result[key]
                if result["unit"] is None:
                    result["unit"] = html_result.get("unit")
            except Exception as err:  # noqa: BLE001 - unknown figures, not fatal
                _LOGGER.debug("AquaTrax HTML fallback failed (%s)", err)
        _LOGGER.debug("AquaTrax usage: %s", result)
        return result

    async def _fetch_dashboard_details(
        self, result: dict[str, float | str | None]
    ) -> None:
        """Fill period + latest-day usage from GetDashboardDetails."""
        async with self._session.get(BASE_URL + DASHBOARD_DETAILS_PATH) as resp:
            data = _portal_json(await resp.text())
        results = data.get("Results") or {}
        tables = results.get("Table") or []
        table2 = (results.get("Table2") or [{}])[0]
        table3 = (results.get("Table3") or [{}])[0]
        table9 = results.get("Table9") or []
        unit_text = table9[0].get("Text") if table9 else None
        factor = _gal_factor(unit_text)
        if unit_text:
            result["unit"] = unit_text
        if tables:
            period = tables[0].get("BillingPeriod")
            if period:
                result["billing_period"] = str(period)
        # Current billing-period usage ("Current Usage" on the dashboard).
        period_value = _num(table2.get("Usagevalue"))
        if period_value is not None:
            result["period_gal"] = period_value * factor
        # Latest day's usage (the daily gauge: Usagevalue on UsageDate).
        today_value = _num(table3.get("Usagevalue"))
        usage_date = _parse_portal_date(table3.get("UsageDate"))
        if today_value is not None:
            result["today_gal"] = today_value * factor
        if usage_date is not None:
            result["usage_date"] = usage_date.isoformat()

    async def _fetch_header_usage(
        self, result: dict[str, float | str | None]
    ) -> None:
        """Fill period usage from GetHeaderUsage ('so far' this period)."""
        async with self._session.get(BASE_URL + HEADER_USAGE_PATH) as resp:
            data = _portal_json(await resp.text())
        rows = ((data.get("Results") or {}).get("Table") or [])
        if not rows:
            return
        # WaterUnitUsageSoFar is in the utility's billing unit (CCF here);
        # the portal's own gallon rendering reuses the same number, so
        # always convert from the unit label, never trust a gallon field.
        factor = _gal_factor(result.get("unit") if isinstance(result.get("unit"), str) else None)
        so_far = _num(rows[0].get("WaterUnitUsageSoFar"))
        if so_far is not None:
            result["period_gal"] = so_far * factor

    async def _fetch_daily_series(
        self, result: dict[str, float | str | None]
    ) -> None:
        """Sum the daily series from GetWaterUsage for today/week/month.

        Mode "D" rows carry DateOfReading + TotalValue (usage that day, in
        the billing unit). Requested for the current calendar month.
        """
        today = date.today()
        month_start = today.replace(day=1)
        week_start = today - timedelta(days=today.weekday())
        request = {
            "Mode": "D",
            "Type": "W",
            "Year": None,
            "HourlyType": "H",
            "FilterDate": today.strftime("%m/%d/%Y"),
            "FromDate": month_start.strftime("%m/%d/%Y"),
            "MeterNumber": None,
        }
        async with self._session.get(
            BASE_URL + WATER_USAGE_PATH, params={"request": json.dumps(request)}
        ) as resp:
            data = _portal_json(await resp.text())
        rows = ((data.get("Results") or {}).get("Table") or [])
        if not rows:
            return
        factor = _gal_factor(result.get("unit") if isinstance(result.get("unit"), str) else None)
        week_total = 0.0
        month_total = 0.0
        saw_week = False
        saw_month = False
        for row in rows:
            day = _parse_portal_date(row.get("DateOfReading"))
            value = _num(row.get("TotalValue"))
            if day is None or value is None:
                continue
            value_gal = value * factor
            if day == today:
                result["today_gal"] = value_gal
                result["usage_date"] = day.isoformat()
            if week_start <= day <= today:
                week_total += value_gal
                saw_week = True
            if month_start <= day <= today:
                month_total += value_gal
                saw_month = True
        if saw_week:
            result["week_gal"] = week_total
        if saw_month:
            result["month_gal"] = month_total

    async def _fetch_usage_html(self) -> dict[str, float | str | None]:
        """Legacy fallback: scrape numbers off the dashboard page text."""
        url = getattr(self, "_dashboard_url", BASE_URL + "/")
        async with self._session.get(url) as resp:
            html = await resp.text()
        parser = _parse_forms(html)
        text = " ".join(parser.text_chunks)
        _LOGGER.debug("AquaTrax dashboard text (first 2000 chars): %s", text[:2000])
        return parse_usage_text(text)

    @property
    def logged_in(self) -> bool:
        return self._logged_in
