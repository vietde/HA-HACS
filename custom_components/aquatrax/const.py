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
# when that fetch fails. IDs verified live 2026-11-07 via
# /common/GetMasterUtilityList — they are NOT sequential and NOT the list
# order (City of San Jose is 28, not 17 as earlier guessed; Crestline
# Village Water District is 17). The order below is the order the portal
# lists them in.
KNOWN_UTILITY_IDS = {
    "East Orange County Water District": "1",
    "City of Fountain Valley": "2",
    "City of American Canyon": "9",
    "City of Newport Beach": "10",
    "City of Lindon": "12",
    "City of Buena Park": "16",
    "Crestline Village Water District": "17",
    "Laguna Beach County Water District": "18",
    "City of Cedar Hills": "19",
    "Myoma Dunes Water Company": "20",
    "Marshall & Polk Rural Water System": "21",
    "City of Morgan Hill": "22",
    "City of Gilroy": "23",
    "City of Goodyear": "24",
    "City of La Marque": "26",
    "City of White Plains": "27",
    "City of San Jose": "28",
    "Rowland Water District": "29",
    "Fairview City": "30",
}
FALLBACK_UTILITIES = list(KNOWN_UTILITY_IDS)

# Units the portal reports usage in (per AquaTrax flyers: CCF or gallons).
UNIT_CCF = "CCF"
UNIT_GAL = "gal"

# 1 CCF (hundred cubic feet) in gallons / cubic feet.
CCF_TO_GAL = 748.05
CCF_TO_FT3 = 100.0
