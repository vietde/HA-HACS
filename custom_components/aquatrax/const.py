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

# Login form field names. These are the standard ASP.NET MVC names for this
# portal; they will be confirmed against the live login page at first setup
# and corrected here if the portal uses different names.
FORM_UTILITY = "UtilityId"
FORM_EMAIL = "Email"
FORM_PASSWORD = "Password"
FORM_REMEMBER_ME = "RememberMe"
FORM_TOKEN = "__RequestVerificationToken"

# Fallback utility list (name -> numeric id is NOT known for most; the
# integration fetches the live dropdown from the login page at setup time
# and uses the option values the portal itself returns). East Orange County
# Water District is confirmed as id 1. The order below is the order the
# portal lists them in.
FALLBACK_UTILITIES = [
    "City of San Jose",
    "City of Fountain Valley",
    "City of Morgan Hill",
    "City of Gilroy",

]

# Units the portal reports usage in (per AquaTrax flyers: CCF or gallons).
UNIT_CCF = "CCF"
UNIT_GAL = "gal"

# 1 CCF (hundred cubic feet) in gallons / cubic feet.
CCF_TO_GAL = 748.05
CCF_TO_FT3 = 100.0
