"""Constants for the AquaTrax integration."""

DOMAIN = "aquatrax"

CONF_UTILITY = "utility"
CONF_UTILITY_ID = "utility_id"
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_UPDATE_INTERVAL = "update_interval"

DEFAULT_UPDATE_INTERVAL_HOURS = 6

BASE_URL = "https://myaquatrax.com"
LOGIN_PATH = "/Account/Login"
# The utility dropdown is NOT in the login page's raw HTML — it is empty
# there and populated by JavaScript from this endpoint (verified live
# 2026-11-07). It returns double-encoded JSON: {"Results": {"Table":
# [{"UtilityId": 28, "Name": "City of San Jose", ...}]}}.
UTILITY_LIST_PATH = "/common/GetMasterUtilityList"

# The dashboard page is a JavaScript app: its numbers are NOT in the page
# HTML. They come from these JSON endpoints (found 2026-11-07 in the
# portal's own public JS bundles /bundles/dashboardcustomjs and
# /bundles/usagejs). All three need only the session cookie; only
# GetWaterUsage takes parameters (a JSON "request" query value).
DASHBOARD_DETAILS_PATH = "/DashboardCustom/GetDashboardDetails"
HEADER_USAGE_PATH = "/Usage/GetHeaderUsage"
WATER_USAGE_PATH = "/Usage/GetWaterUsage"

# Login form field names — exact names read from the live login page HTML
# (curl, 2026-11-07). The form (#loginFormID) POSTs to /Account/Login and
# carries hidden fields Mfe ("False"), __RequestVerificationToken,
# utilityId ("0" until a utility is picked), InvoiceCoudstatus (""),
# IsRegistration ("False"), IsSSOEnabled ("0"). api.py preserves those
# hidden values verbatim from the form and only overrides utilityId,
# UserName, Password and RememberMe — never hardcode the others (an
# earlier build posted IsRegistration=true / IsSSOEnabled=1 and failed).
FORM_UTILITY = "utilityId"
FORM_EMAIL = "UserName"
FORM_PASSWORD = "Password"
FORM_REMEMBER_ME = "RememberMe"
FORM_TOKEN = "__RequestVerificationToken"

# Fallback utility list (name -> numeric id). The integration fetches the
# live list from UTILITY_LIST_PATH at setup time; this map is the fallback
# when that fetch fails, and the setup form only offers utilities in this
# map. IDs verified live 2026-11-07 via /common/GetMasterUtilityList —
# they are NOT sequential (City of San Jose is 28, not 17 as earlier
# guessed). Ngot asked 2026-11-07 for just these three in the list:
# City of Gilroy, City of San Jose, City of Fountain Valley.
KNOWN_UTILITY_IDS = {
    "City of Gilroy": "23",
    "City of San Jose": "28",
    "City of Fountain Valley": "2",
}
FALLBACK_UTILITIES = list(KNOWN_UTILITY_IDS)

# Units the portal reports usage in (per AquaTrax flyers: CCF or gallons).
UNIT_CCF = "CCF"
UNIT_GAL = "gal"

# 1 CCF (hundred cubic feet) in gallons / cubic feet.
CCF_TO_GAL = 748.05
CCF_TO_FT3 = 100.0
