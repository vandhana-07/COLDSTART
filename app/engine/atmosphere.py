"""
atmosphere.py -- solar geometry, altitude-dependent irradiance, ISA standard atmosphere.
========================================================================================
Fixes audit finding A1: the previous code applied SURFACE irradiance to a payload at
26 km. This module computes irradiance that actually varies with altitude.

Reference case used for validation (tests/test_atmosphere.py):
    clear-sky sea-level noon irradiance for Chennai in October should land in the
    range the real GFS surface forecast reports (~800-1000 W/m2), and the
    above-atmosphere value should approach the solar constant.
"""

import math

from . import params as P


# ---------------------------------------------------------------------------
# SOLAR GEOMETRY
# ---------------------------------------------------------------------------
def solar_elevation_deg(lat_deg, lon_deg, when_utc):
    """NOAA low-precision solar position algorithm.

    SOURCE: NOAA Solar Calculator equations (public standard).
    Returns the sun's elevation above the horizon in degrees. Negative = night.
    """
    day_of_year = when_utc.timetuple().tm_yday
    hour = when_utc.hour + when_utc.minute / 60.0 + when_utc.second / 3600.0

    g = 2 * math.pi / 365.0 * (day_of_year - 1 + (hour - 12) / 24.0)
    declination = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g)
                   - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
                   - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    equation_of_time = 229.18 * (0.000075 + 0.001868 * math.cos(g)
                                 - 0.032077 * math.sin(g)
                                 - 0.014615 * math.cos(2 * g)
                                 - 0.040849 * math.sin(2 * g))
    true_solar_time = (hour * 60 + equation_of_time + 4 * lon_deg) % 1440
    hour_angle = math.radians(true_solar_time / 4 - 180)
    lat = math.radians(lat_deg)

    cos_zenith = (math.sin(lat) * math.sin(declination)
                  + math.cos(lat) * math.cos(declination) * math.cos(hour_angle))
    return math.degrees(math.asin(max(-1.0, min(1.0, cos_zenith))))


def extraterrestrial_irradiance(day_of_year):
    """Inverse-square correction to the solar constant.

    SOURCE: standard eccentricity approximation, +/- 3.3%.
    """
    return P.SOLAR_CONSTANT * (1.0 + 0.033 * math.cos(2 * math.pi * day_of_year / 365.0))


def atmospheric_pressure_ratio(altitude_km):
    """Fraction of sea-level atmospheric mass above a given altitude.

    SOURCE: ISA / exponential atmosphere with an 8500 m scale height.
    At 26 km this is ~0.047, i.e. ~95% of the atmosphere is below the payload.
    """
    alt_m = max(0.0, altitude_km * 1000.0)
    return math.exp(-alt_m / P.SCALE_HEIGHT_M)


def direct_irradiance_wm2(altitude_km, elevation_deg, day_of_year):
    """Beam irradiance available at altitude, clear sky.

    Attenuation = Beer-Lambert with optical airmass, scaled by the fraction of
    atmosphere still ABOVE the payload:

        I = I_extr * exp( -m * tau0 * p_ratio )

    where m = 1/sin(elevation) capped at 38 (standard airmass limit at the horizon).

    Reference check (in tests): at 0 km with the sun overhead this should give
    roughly 1361 * exp(-0.15) ~= 1171 W/m2, consistent with clear-sky noon values;
    at 26 km it should approach the extraterrestrial value.
    """
    if elevation_deg <= 0.0:
        return 0.0
    i_extr = extraterrestrial_irradiance(day_of_year)
    sin_e = max(math.sin(math.radians(elevation_deg)), 1.0 / 38.0)
    airmass = 1.0 / sin_e
    p_ratio = atmospheric_pressure_ratio(altitude_km)
    return i_extr * math.exp(-airmass * P.ATMOSPHERE_OPTICAL_DEPTH * p_ratio)


def panel_power_w(altitude_km, elevation_deg, day_of_year, area_m2,
                  efficiency=P.PANEL_EFFICIENCY,
                  view_factor=P.DEFAULT_PANEL_VIEW_FACTOR):
    """Electrical power from a horizontally-hung panel.

    view_factor bundles cosine loss from imperfect attitude, partial shading and
    cell mismatch into one documented ASSUMPTION (see params.py). It is a named
    uncertainty axis in the stress-test engine -- not a fudge factor.

    NOTE / LIMITATION: this is a clear-sky model. It has no cloud term, which is
    deliberate: above the float altitude there is no cloud, and modelling cloud
    below would require a vertical cloud profile the forecast does not give us.
    """
    if area_m2 <= 0.0:
        return 0.0
    beam = direct_irradiance_wm2(altitude_km, elevation_deg, day_of_year)
    return beam * area_m2 * efficiency * view_factor


def isa_temperature_c(altitude_km):
    """ISA standard-atmosphere temperature, used ONLY above the forecast ceiling.

    SOURCE: International Standard Atmosphere, troposphere lapse rate 6.5 K/km.
    Troposphere: T = 15 - 6.5*h (h in km), valid to 11 km.
    Above 11 km the ISA is isothermal at -56.5 C up to 20 km, then warms.
    Used as an explicitly-labelled fallback when no forecast level exists.
    """
    h = max(0.0, altitude_km)
    if h <= 11.0:
        return 15.0 - 6.5 * h
    if h <= 20.0:
        return -56.5
    if h <= 32.0:
        # stratosphere warming, ~+1.0 K/km
        return -56.5 + 1.0 * (h - 20.0)
    return -44.5


def isa_pressure_hpa(altitude_km):
    """ISA pressure, for reference/altitude cross-checks.

    NOTE ON UNITS (a real bug caught by tests/test_engine.py T7): the barometric
    formula requires altitude in METRES. The lapse term is 0.0065 K/m, so passing
    kilometres gives pressures that are wrong by an order of magnitude in the
    stratosphere. Verified: 0 km -> 1013.25, 11 km -> 226.3, 20 km -> 54.7 hPa.
    """
    h_m = max(0.0, altitude_km * 1000.0)
    t0, lapse, p0 = 288.15, 0.0065, 1013.25
    if h_m <= 11000.0:
        return p0 * (1.0 - lapse * h_m / t0) ** 5.2559
    p11 = p0 * (1.0 - lapse * 11000.0 / t0) ** 5.2559
    # Isothermal layer 11-20 km: scale height H = R*T/g = 287.05*216.65/9.80665
    # = 6341 m. The gravitational term is essential -- omitting it makes 26 km
    # read 178 hPa instead of the correct ~20 hPa.
    scale_height_m = 287.05 * 216.65 / 9.80665
    return p11 * math.exp(-(h_m - 11000.0) / scale_height_m)
