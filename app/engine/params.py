"""
params.py -- SINGLE SOURCE OF TRUTH for every constant in COLDSTART.
==========================================================================
Every number here is tagged:

  SOURCE      : a published, citable value (datasheet, standard, physical constant)
  ASSUMPTION  : an engineering choice made by this team; uncertain; stress-tested
  DERIVED     : computed from other values here

If a number is not tagged, that is a bug. Nothing in the engine may hardcode a
physical constant outside this file -- so a judge can audit every input in one place.
"""

# ===========================================================================
# PHYSICAL CONSTANTS  (SOURCE: SI / CODATA)
# ===========================================================================
STEFAN_BOLTZMANN = 5.670374419e-8      # W/(m^2 K^4)
SOLAR_CONSTANT = 1361.0                # W/m^2, mean extraterrestrial irradiance at 1 AU
T_SPACE_K = 3.0                        # K, cosmic microwave background / deep-sky sink
KELVIN_OFFSET = 273.15
SECONDS_PER_HOUR = 3600.0


def c_to_k(c):
    return c + KELVIN_OFFSET


def k_to_c(k):
    return k - KELVIN_OFFSET


# ===========================================================================
# BATTERY  --  18650 Li-ion
# ===========================================================================
# SOURCE: manufacturer datasheet discharge curves (Panasonic NCR18650B class).
# Capacity expressed as a FRACTION of the 20 C rated capacity.
CAPACITY_VS_TEMP = [
    (-60, 0.35),
    (-40, 0.45),
    (-20, 0.60),
    (-10, 0.70),
    (0,   0.85),
    (20,  1.00),
]

# SOURCE: same datasheet family. 3400 mAh x 3.6 V nominal.
CELL_WH = 12.24                        # Wh per cell, nominal
CELL_AH = 3.4                          # Ah per cell, nominal

CELL_MASS_KG = 0.045                   # SOURCE: typical 18650, 45 g
CELL_COST_INR = 250.0                  # ASSUMPTION: India retail, 3400 mAh 18650

# SOURCE: Li-ion datasheets / literature.
CELL_CP_J_PER_KG_K = 1000.0            # specific heat capacity of a Li-ion cell
PACK_INACTIVE_MASS_FRACTION = 0.30     # ASSUMPTION: holders, tabs, wiring, BMS

# ASSUMPTION: manufacturer continuous-discharge guidance for high-capacity 18650 cells.
# 1C continuous is conservative and defensible for a 3400 mAh energy cell.
C_RATE_MAX = 1.0

# ASSUMPTION: below this temperature the cells may not be discharged at all without
# risking lithium plating / permanent damage. Many datasheets list -20 C discharge
# minimum. Kept as a design parameter and stress-tested.
DEFAULT_MIN_OPERATING_C = -20.0

# SOURCE: Li-ion datasheets typically specify a maximum operating temperature of
# 60 C; sustained operation above it accelerates ageing and risks thermal runaway.
# This matters because a WELL-insulated box with self-heating electronics can
# overheat even in the stratosphere -- over-insulating is a real failure mode.
DEFAULT_MAX_OPERATING_C = 60.0

# ASSUMPTION: Li-ion must not be charged below 0 C (lithium plating). This is a
# documented industry constraint, not a modelled guess.
CHARGE_MIN_TEMP_C = 0.0

# ASSUMPTION: round-trip electrical losses when charging from the panel.
CHARGE_EFFICIENCY = 0.95


# ===========================================================================
# THERMAL
# ===========================================================================
# SOURCE: thermal conductivity values from manufacturer data.
#   aerogel blanket ~0.018, XPS foam ~0.030, thermocol/styrofoam ~0.035 W/(m*K)
K_INSULATION = {"aerogel": 0.018, "xps": 0.030, "xps_foam": 0.030, "thermocol": 0.035}
DEFAULT_K_INSULATION = 0.030           # ASSUMPTION: XPS foam is what a student buys

INSULATION_DENSITY_KG_M3 = {"aerogel": 150.0, "xps": 35.0, "thermocol": 20.0}
DEFAULT_INSULATION_DENSITY = 35.0      # ASSUMPTION: XPS
INSULATION_CP_J_PER_KG_K = 1300.0      # SOURCE: polymer foam, literature range 1200-1500
INSULATION_COST_INR_PER_M2_MM = 80.0   # ASSUMPTION: retail

# ASSUMPTION: the effective radiant environment the OUTER surface sees.
# At 26 km the payload sees cold space above, warmer Earth below and the horizon at
# the sides. Modelling that in full 3-D is out of scope; we parameterise it as an
# effective radiant temperature offset from ambient. A positive value means the
# surroundings radiate LESS than ambient (net cooling to space).
# This is a first-order parameterisation and a NAMED uncertainty axis.
DEFAULT_RADIANT_OFFSET_C = 10.0        # surroundings behave as if 10 K colder than air

DEFAULT_EMISSIVITY = 0.90              # ASSUMPTION: foam / tape surface
HOUSING_CP_J_PER_KG_K = 900.0          # SOURCE: aluminium/polymer structure, literature
HOUSING_MASS_KG = 0.12                 # ASSUMPTION: box, fasteners, tray for a small payload

# ASSUMPTION: fraction of payload electrical power that ends up as heat INSIDE the box.
# Radios and cameras mostly do. This is a real and often-forgotten heat source.
PAYLOAD_HEAT_FRACTION = 0.60


# ===========================================================================
# HEATER + AVIONICS
# ===========================================================================
DEFAULT_HEATER_MAX_W = 5.0             # ASSUMPTION: small resistive film / cartridge heater
HEATER_MASS_KG = 0.03                  # ASSUMPTION
HEATER_COST_INR = 150.0                # ASSUMPTION
THERMOSTAT_MASS_KG = 0.02              # ASSUMPTION
THERMOSTAT_COST_INR = 200.0            # ASSUMPTION
THERMOSTAT_HYSTERESIS_C = 1.0          # ASSUMPTION: on/off band, avoids chattering

WIRING_MASS_KG = 0.05                  # ASSUMPTION
WIRING_COST_INR = 150.0                # ASSUMPTION


# ===========================================================================
# SOLAR PANEL
# ===========================================================================
PANEL_EFFICIENCY = 0.18                # ASSUMPTION: silicon cells, typical hobby grade
PANEL_MASS_PER_M2_KG = 1.5             # ASSUMPTION: encapsulated cells + backing
PANEL_COST_INR_PER_M2 = 12000.0        # ASSUMPTION: retail
# ASSUMPTION: a free-hanging payload cannot hold perfect sun tracking. This factor
# represents average cosine loss, partial shading, and cell mismatch. Stress-tested.
DEFAULT_PANEL_VIEW_FACTOR = 0.70

# SOURCE: clear-sky vertical optical depth at sea level for broadband solar, literature.
ATMOSPHERE_OPTICAL_DEPTH = 0.15
SCALE_HEIGHT_M = 8500.0                # SOURCE: ISA standard atmosphere


# ===========================================================================
# MISSION DEFAULT
# ===========================================================================
DEFAULT_BOX_AREA_M2 = 0.0864           # ASSUMPTION: 12 x 12 x 12 cm outer box
DEFAULT_BOX_VOLUME_M3 = 0.001728       # 0.12^3

# ASSUMPTION: a latex sounding balloon flight carrying ~1 kg.
ASCENT_MIN = 120.0                     # minutes to reach float altitude
BURST_ALT_KM = 26.0                    # ASSUMPTION
EARTH_RADIUS_KM = 6371.0               # SOURCE: IUGG mean Earth radius 6371.0088 km
FLOAT_MIN = 660.0                      # minutes at altitude
DESCENT_MIN = 45.0                     # minutes under parachute
DEFAULT_DURATION_MIN = ASCENT_MIN + FLOAT_MIN + DESCENT_MIN

DEFAULT_RESERVE_FRACTION = 0.10        # ASSUMPTION: never plan to use the last 10%


# ===========================================================================
# VALIDATION TOLERANCES  (used by tests/)
# ===========================================================================
TOL_EXACT = 1e-9
TOL_PERCENT = 0.01                     # 1% agreement against analytical references

# ---------------------------------------------------------------------------
# ENGINE IDENTITY -- quoted in the report so a run can be tied to a code state.
# ---------------------------------------------------------------------------
ENGINE_VERSION = "coldstart-engine-1.0"


def as_dict():
    """Every module-level constant, for the report's assumptions section.

    Only upper-case names are exported so helper functions and imports are not
    swept in. This is what a judge reads to audit the simulation's inputs.
    """
    g = globals()
    out = {}
    for name, val in g.items():
        if name.isupper() and not name.startswith("_") and not callable(val):
            if isinstance(val, (int, float, str, bool, list, tuple, dict, type(None))):
                out[name] = val
    return out
