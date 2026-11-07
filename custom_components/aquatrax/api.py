"""Async client for the AquaTrax customer portal (myaquatrax.com).

The portal is a server-rendered ASP.NET MVC site with no public REST API,
so this client reproduces what a browser does: fetch the login page, pick
the water utility from its dropdown, and POST the sign-in form, then read
the usage figures off the dashboard page.

Nothing here is tested against a real account yet (no account exists at
build time). Parsing is deliberately defensive: unknown page shapes yield
``None`` figures instead of exceptions, and the raw dashboard text is kept
at DEBUG level so the selectors can be tuned after the first real login.
"""

from __future__ import annotations

import logging
import re
from html.parser import HTMLParser
from typing import Any

from aiohttp import ClientSession

from .const import (
    BASE_URL,
    CCF_TO_GAL,
    FORM_EMAIL,
    FORM_PASSWORD,
    FORM_REMEMBER_ME,
    FORM_TOKEN,
    FORM_UTILITY,
    LOGIN_PATH,
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


class AquaTraxClient:
    """Minimal async client for the AquaTrax portal."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session
        self._logged_in = False

    async def fetch_utilities(self) -> dict[str, str]:
        """Return {utility display name: numeric id} from the login page."""
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

    async def login(self, utility_id: str, email: str, password: str) -> bool:
        """Sign in with the portal form. Returns True on success."""
        try:
            async with self._session.get(BASE_URL + LOGIN_PATH) as resp:
                html = await resp.text()
                login_url = str(resp.url)
        except Exception as err:
            raise AquaTraxConnectionError(f"Could not load login page: {err}") from err

        parser = _parse_forms(html)
        login_form = None
        for form in parser.forms:
            if "login" in (form.get("action") or "").lower() or FORM_EMAIL in form.get("inputs", {}):
                login_form = form
                break
        if login_form is None and parser.forms:
            login_form = parser.forms[0]
        if login_form is None:
            raise AquaTraxConnectionError("No sign-in form found on the login page")

        data: dict[str, str] = {}
        inputs = login_form.get("inputs", {})
        if FORM_TOKEN in inputs:
            data[FORM_TOKEN] = inputs[FORM_TOKEN]["value"]
        # Preserve any other hidden fields (e.g. return URL).
        for name, field in inputs.items():
            if field["type"] == "hidden" and name not in data:
                data[name] = field["value"]
        data[FORM_UTILITY] = utility_id
        data[FORM_EMAIL] = email
        data[FORM_PASSWORD] = password
        data[FORM_REMEMBER_ME] = "true"

        action = login_form.get("action") or LOGIN_PATH
        post_url = action if action.startswith("http") else BASE_URL + action
        try:
            async with self._session.post(
                post_url, data=data, allow_redirects=True
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
        """Fetch the dashboard and extract usage figures (gallons)."""
        url = getattr(self, "_dashboard_url", BASE_URL + "/")
        try:
            async with self._session.get(url) as resp:
                html = await resp.text()
        except Exception as err:
            raise AquaTraxConnectionError(f"Could not load dashboard: {err}") from err
        parser = _parse_forms(html)
        text = " ".join(parser.text_chunks)
        _LOGGER.debug("AquaTrax dashboard text (first 2000 chars): %s", text[:2000])
        result = parse_usage_text(text)
        result["dashboard_url"] = url
        return result

    @property
    def logged_in(self) -> bool:
        return self._logged_in
