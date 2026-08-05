"""
Plain-language calculation procedure notes, for the Scientist-facing "View
calculation procedure" reference panel (Sprint follow-up: "make it visible
in layman [terms]").

This is presentation content only -- it explains, in clearer language, the
exact same formulas already implemented in calculation_engine.py. It does
NOT introduce any new engineering fact, limit, or threshold: every formula
described here is the literal formula in that file, cross-checked against
it when this was written. If calculation_engine.py's formula for a test
ever changes, this file must be updated to match -- see the test below
that keeps the two in sync.

Each entry has:
  summary      -- one or two plain sentences: what this test is checking
                   and why it matters for the cable.
  measurement  -- what the Scientist/Assistant physically does or reads
                   off an instrument to get the raw numbers.
  formula      -- the calculation itself, spelled out with each symbol
                   named in plain words (not just the code's variable names).
"""
from typing import Dict, Optional, TypedDict


class ProcedureNote(TypedDict):
    summary: str
    measurement: str
    formula: str


PROCEDURE_NOTES: Dict[str, ProcedureNote] = {
    "TEST-0001": {
        "summary": "Checks that the conductor lets current flow with low enough "
                    "resistance -- too much resistance means the cable wastes "
                    "power as heat and can overheat in normal use.",
        "measurement": "A length of the conductor is connected to a resistance-measuring "
                        "bridge, which reads its resistance directly. The room temperature "
                        "at the time of the test and the exact length tested are also noted, "
                        "because both affect the reading.",
        "formula": "Resistance rises with temperature, so the raw reading is first adjusted "
                    "down (or up) to what it would read at a standard 20°C, using a correction "
                    "factor (kt) looked up from the room temperature. It's then scaled to the "
                    "standard unit of ohms per kilometre:\n\n"
                    "Corrected Resistance (ohm/km) = (Observed Resistance in mOhm ÷ 1000) × kt "
                    "÷ Specimen Length (m) × 1000\n\n"
                    "The result must come out at or below the limit for this cable's conductor "
                    "size -- a lower number is better (less resistance).",
    },
    "TEST-0002": {
        "summary": "Checks that the PVC insulation around the conductor is thick enough "
                    "everywhere to properly insulate and protect it -- too thin in even one "
                    "spot is a weak point.",
        "measurement": "The insulation thickness is measured at several points around a "
                        "cross-section of the core using a microscope or thickness gauge -- "
                        "5 separate readings are taken.",
        "formula": "Two numbers are checked against the standard: the average of all readings, "
                    "and the single lowest (thinnest) reading.\n\n"
                    "Average thickness = sum of all 5 readings ÷ 5\n\n"
                    "The average must meet or exceed the nominal thickness for this cable's "
                    "conductor size, AND the thinnest single reading must not fall below a "
                    "floor value (the nominal thickness minus an allowed tolerance). Both "
                    "conditions have to hold -- a good average can't hide one thin spot.",
    },
    "TEST-0003": {
        "summary": "Checks how much pulling force the insulation (or sheath) material can "
                    "take before it snaps -- material that's too weak could split or tear "
                    "in service.",
        "measurement": "A dumbbell-shaped strip is cut from the insulation or sheath, its "
                        "width and thickness are measured, and it's pulled in a tensile "
                        "testing machine until it breaks. The force at breaking point is "
                        "recorded.",
        "formula": "Tensile Strength (N/mm²) = Breaking Load (N) ÷ Cross-sectional Area (mm²), "
                    "where Area = Width × Thickness.\n\n"
                    "A higher result is better -- the material must reach at least the minimum "
                    "strength required for its insulation/sheath type.",
    },
    "TEST-0004": {
        "summary": "Measures how much the same test strip can stretch before it breaks -- "
                    "a material that's too stiff/brittle (doesn't stretch much) is more "
                    "likely to crack under bending or thermal movement.",
        "measurement": "Two reference marks a known distance apart are put on the same "
                        "tensile-test strip used for Tensile Strength (above). As the machine "
                        "pulls the strip apart, the distance between the marks is measured "
                        "again right at the moment it breaks.",
        "formula": "Elongation (%) = ((Length at Break − Initial Gauge Length) ÷ Initial Gauge "
                    "Length) × 100\n\n"
                    "A higher percentage means the material stretched further before breaking. "
                    "It must reach at least the minimum required for its insulation/sheath type.",
    },
    "TEST-0005": {
        "summary": "Confirms the finished cable can safely hold up to a high test voltage at "
                    "normal room conditions without the insulation breaking down internally.",
        "measurement": "The complete cable has 3kV (AC, 50Hz) applied across it for 5 minutes. "
                        "The Scientist watches for any breakdown or flashover (a visible or "
                        "audible electrical failure through the insulation).",
        "formula": "This is a pass/fail observation, not a calculated number: the cable passes "
                    "only if no breakdown or flashover is seen during the 5-minute hold.",
    },
    "TEST-0006": {
        "summary": "Checks how well the insulation resists letting current leak through it "
                    "sideways (rather than along the conductor) -- higher resistance means "
                    "better, safer insulation.",
        "measurement": "A length of cable is connected to a megohmmeter, which applies a "
                        "test voltage and reads the insulation resistance directly in "
                        "megohms. The specimen's length and its overall/conductor diameters "
                        "are also measured, because resistance depends on the insulation's "
                        "geometry as well as its material.",
        "formula": "The raw megohm reading is converted into \"volume resistivity\" -- a "
                    "material property independent of the specimen's size -- using the ratio "
                    "of the outer diameter (D) to the conductor diameter (d):\n\n"
                    "Volume Resistivity (ohm·cm) = 2π × Length (m) × Insulation Resistance "
                    "(MΩ) × 10⁸ ÷ ln(D ÷ d)\n\n"
                    "A higher result means better insulation. It must meet or exceed the "
                    "minimum for this insulation type.",
    },
    "TEST-0008": {
        "summary": "Measures how much oxygen has to be in the air before the material will "
                    "keep burning on its own -- a higher number means the material is harder "
                    "to sustain a flame on, which matters for fire safety.",
        "measurement": "A specimen is burned in a controlled chamber where the oxygen "
                        "concentration can be dialled in. The Oxygen Index is the lowest % "
                        "of oxygen (mixed with nitrogen) that still lets the specimen keep "
                        "burning like a candle -- read directly off the test apparatus.",
        "formula": "This is a direct instrument reading, not a calculation. A higher % is "
                    "better -- it must meet or exceed the minimum required.",
    },
    "TEST-0009": {
        "summary": "For fire-retardant cable types, checks how much acidic (corrosive) gas "
                    "is given off when the material burns -- less acid gas means less "
                    "corrosion damage to nearby equipment in a real fire.",
        "measurement": "A sample of known weight is burned, and the acidic gas produced is "
                        "captured and dissolved in water, then measured by titration -- adding "
                        "a reagent (of known strength, the \"titration factor\") drop by drop "
                        "until a chemical endpoint is reached, and recording how much reagent "
                        "was used (compared to a blank/reference titration).",
        "formula": "HCl (%) = (36.5 × (Titration Volume B − Titration Volume A) × Titration "
                    "Factor × 5) × 100 ÷ 1000\n\n"
                    "A lower percentage is better -- it must not exceed the maximum allowed "
                    "by weight.",
    },
    "TEST-0010": {
        "summary": "Combines the flammability and oxygen-index behaviour into a single "
                    "temperature rating -- the minimum temperature at which the material "
                    "will support burning when 21% oxygen (normal air) is present.",
        "measurement": "Determined on specialised test apparatus per the standard's method; "
                        "CTL records the resulting index value directly rather than a set of "
                        "intermediate readings.",
        "formula": "Direct entry of the measured Temperature Index in °C. A higher value is "
                    "better -- it must meet or exceed the minimum required.",
    },
    "TEST-0011": {
        "summary": "For copper conductors, checks the wire was properly \"annealed\" (heat-"
                    "softened) after being drawn/stranded -- under-annealed copper is too "
                    "stiff and can crack when the cable is bent or terminated.",
        "measurement": "A length of the copper wire is marked with a gauge length, then "
                        "pulled in a tensile machine until it breaks; the distance between "
                        "marks after breaking is measured.",
        "formula": "Elongation (%) = ((Length After Break − Gauge Length) ÷ Gauge Length) × 100\n\n"
                    "The minimum required elongation depends on the wire's diameter (thinner "
                    "wires are allowed a different minimum than thicker ones) -- a higher "
                    "result is better.",
    },
    "TEST-0012": {
        "summary": "For aluminium conductors, checks the wire is strong enough in tension "
                    "not to snap under normal handling and installation stresses.",
        "measurement": "A single wire's diameter is measured, then it's pulled to breaking "
                        "point in a tensile machine and the breaking load recorded. Whether "
                        "the wire was tested before or after stranding (twisting the wires "
                        "together) is also noted, since the allowed minimum differs slightly.",
        "formula": "Tensile Strength (N/mm²) = Breaking Load (N) ÷ Cross-sectional Area (mm²), "
                    "where Area = π × (Wire Diameter ÷ 2)².\n\n"
                    "The minimum required depends on the aluminium grade (0 / H2 / H4) and "
                    "whether it was measured before or after stranding.",
    },
    "TEST-0013": {
        "summary": "For aluminium conductors, checks the wire can be wrapped tightly around "
                    "itself (simulating installation bending) without snapping -- a wire that "
                    "breaks here is too brittle for safe installation.",
        "measurement": "A single wire is wound tightly around a mandrel (rod) of a specified "
                        "diameter for a set number of turns. The Scientist observes whether "
                        "the wire breaks during winding.",
        "formula": "This is a pass/fail observation, not a calculated number: the wire passes "
                    "only if it does not break.",
    },
    "TEST-0014": {
        "summary": "Checks that the outer sheath (the protective jacket over all the cores) "
                    "is thick enough everywhere -- too thin anywhere is a weak point against "
                    "mechanical damage and moisture ingress.",
        "measurement": "Same method as Insulation Thickness (above), but measured on the "
                        "outer sheath instead: 5 thickness readings taken around a cross-"
                        "section.",
        "formula": "Average thickness = sum of all 5 readings ÷ 5.\n\n"
                    "The average must meet or exceed the nominal sheath thickness for this "
                    "cable's size and core count, AND the single thinnest reading must not "
                    "fall below a floor value (the nominal thickness minus an allowed "
                    "tolerance, which is a slightly larger tolerance than insulation gets).",
    },
    "TEST-0015": {
        "summary": "Checks how much the material's tensile strength has weakened after being "
                    "artificially aged (baked) -- cable insulation has to stay strong over "
                    "its service life, not just when new.",
        "measurement": "A specimen is baked in an oven (80±2°C for 7 days) to simulate long-"
                        "term ageing, then pulled to breaking point exactly like the ordinary "
                        "Tensile Strength test. The result is compared against that same "
                        "core/sheath's tensile strength measured before ageing.",
        "formula": "Tensile Strength After Ageing (N/mm²) = Breaking Load (N) ÷ (Width × "
                    "Thickness)\n\n"
                    "Variation (%) = |Before-Ageing Value − After-Ageing Value| ÷ Before-"
                    "Ageing Value × 100\n\n"
                    "A smaller variation is better -- it must not exceed the maximum allowed "
                    "swing (up or down) for this material type.",
    },
    "TEST-0016": {
        "summary": "Checks how much the material's stretchiness (elongation) has changed "
                    "after the same artificial-ageing bake -- material that gets too brittle "
                    "with age is a long-term reliability risk.",
        "measurement": "The same aged specimen used for the Ageing Tensile test above also "
                        "has its elongation measured at breaking point, exactly like the "
                        "ordinary Elongation at Break test.",
        "formula": "Elongation After Ageing (%) = ((Length at Break − Initial Gauge Length) ÷ "
                    "Initial Gauge Length) × 100\n\n"
                    "Variation (%) = |Before-Ageing Value − After-Ageing Value| ÷ Before-Ageing "
                    "Value × 100\n\n"
                    "A smaller variation is better -- it must not exceed the maximum allowed "
                    "swing for this material type.",
    },
    "TEST-0017": {
        "summary": "Checks how much weight the material loses when heated -- significant "
                    "weight loss usually means plasticiser (the additive that keeps PVC "
                    "flexible) is evaporating out, which makes the material go stiff and "
                    "brittle over time.",
        "measurement": "A specimen of known surface area is weighed, baked in an oven for a "
                        "set time/temperature, then weighed again once cooled.",
        "formula": "Loss of Mass (mg/cm²) = (Initial Weight − Final Weight) ÷ Surface Area\n\n"
                    "A smaller loss is better -- it must not exceed the maximum allowed for "
                    "this material type.",
    },
    "TEST-0018": {
        "summary": "Checks how much the material shrinks when heated -- excessive shrinkage "
                    "can expose the conductor at cable ends or joints, or pull insulation "
                    "away from where it's needed.",
        "measurement": "A marked length of specimen is measured, heated to a set temperature "
                        "for a set time, then measured again once cooled.",
        "formula": "Shrinkage (%) = ((Length Before − Length After) ÷ Length Before) × 100\n\n"
                    "A smaller percentage is better -- it must not exceed the maximum allowed.",
    },
    "TEST-0019": {
        "summary": "Checks the material doesn't crack when suddenly exposed to high heat -- "
                    "simulates a hot environment or nearby heat source without a long soak.",
        "measurement": "A wound specimen is placed in an oven at 150±2°C for 1 hour, then "
                        "examined closely for any visible cracks or surface scaling.",
        "formula": "This is a pass/fail observation, not a calculated number: the material "
                    "passes only if no cracks or scaling are seen.",
    },
    "TEST-0020": {
        "summary": "Checks how much the material softens and deforms under a heated, loaded "
                    "point -- material that deforms too easily when warm could get squashed "
                    "or damaged if the cable runs hot in service.",
        "measurement": "A weighted indenter presses into the heated specimen. Thickness is "
                        "measured right at the indentation point (2 readings) and again a "
                        "short distance away where the indenter didn't touch, as a baseline "
                        "(4 readings).",
        "formula": "Depth of Indentation (%) = 100 − (Average Thickness at Indent Point ÷ "
                    "Average Baseline Thickness × 100)\n\n"
                    "A smaller percentage (less deformation) is better -- it must not exceed "
                    "the maximum allowed for this material type.",
    },
    "TEST-0021": {
        "summary": "Checks how long the material can withstand a fixed high temperature "
                    "before it starts to visibly break down -- longer is better, and shows "
                    "the material has enough thermal margin for its rated operating "
                    "temperature.",
        "measurement": "A specimen is placed in an oven at a fixed elevated temperature and "
                        "watched continuously; the number of minutes until visible failure "
                        "(cracking, colour change signalling breakdown, etc.) is timed and "
                        "recorded.",
        "formula": "Direct timed reading, in minutes -- not a calculation. It must meet or "
                    "exceed the minimum required for this material type.",
    },
    "TEST-0022": {
        "summary": "For fire-retardant cable types, measures how much smoke the material "
                    "produces when it burns -- thick smoke reduces visibility and makes "
                    "escape harder in a real building fire.",
        "measurement": "A specimen is burned in a closed chamber and a light beam is shone "
                        "through the smoke; a sensor on the other side records what % of the "
                        "light is blocked, read at 15-second intervals for 4 minutes (17 "
                        "readings total).",
        "formula": "Smoke Density Rating (%) = average of all the light-absorption readings.\n\n"
                    "A lower rating (less light blocked, i.e. less smoke) is better -- it "
                    "must not exceed the maximum allowed.",
    },
    "TEST-0023": {
        "summary": "For fire-retardant cable types, checks the cable is self-extinguishing -- "
                    "it should stop burning on its own soon after the test flame is taken "
                    "away, rather than keep burning and spreading fire.",
        "measurement": "A test flame is applied to a mounted specimen for a set time, then "
                        "removed. A stopwatch times how long the specimen keeps burning on "
                        "its own after that.",
        "formula": "Direct timed reading, in seconds -- not a calculation. A shorter time is "
                    "better -- it must not exceed the maximum allowed.",
    },
    "TEST-0024": {
        "summary": "Same flammability test as above, but checks how far up the specimen the "
                    "fire actually reached -- a fire that only travels a short distance shows "
                    "the material limits flame spread.",
        "measurement": "After the flammability burn test, the length of specimen left "
                        "completely undamaged (measured up from the lower clamp) is measured "
                        "with a ruler.",
        "formula": "Direct measured reading, in mm -- not a calculation. A longer undamaged "
                    "length is better -- it must meet or exceed the minimum required.",
    },
    "TEST-0025": {
        "summary": "A tougher version of the High Voltage test -- checks the cable can hold "
                    "up to high voltage even after being soaked in water, which is a much "
                    "harder condition than dry, room-temperature testing and closer to how "
                    "the cable might actually get wet in service.",
        "measurement": "The cable is submerged in water at 60±3°C for 24 hours to let "
                        "moisture work into it, then two separate voltage tests are applied "
                        "while still in the water bath: first an AC test (3kV raised to 6kV "
                        "over 10 seconds, held 5 minutes), then a DC test (1.2kV held for 240 "
                        "hours). The Scientist watches for breakdown or flashover at each "
                        "stage.",
        "formula": "This is a pass/fail observation, not a calculated number: the cable "
                    "passes only if no breakdown or flashover occurs in either the AC or the "
                    "DC stage.",
    },
    "TEST-0026": {
        "summary": "For outdoor-rated cables, checks the sheath doesn't crack when bent in "
                    "cold conditions -- outdoor cables need to survive winter installation "
                    "and handling without becoming brittle.",
        "measurement": "A specimen is cooled to a specified low temperature, then bent "
                        "around a mandrel of a specified diameter, and examined for cracks "
                        "or scaling.",
        "formula": "This is a pass/fail observation, not a calculated number: the material "
                    "passes only if no cracks or scaling are seen.",
    },
    "TEST-0027": {
        "summary": "For outdoor-rated cables, checks the sheath doesn't shatter or crack "
                    "when struck in cold conditions -- simulates rough handling (e.g. being "
                    "dropped or knocked) in winter.",
        "measurement": "A specimen is cooled to a specified low temperature, then struck "
                        "with a specified impact (a falling weight/hammer test), and examined "
                        "for cracks or scaling.",
        "formula": "This is a pass/fail observation, not a calculated number: the material "
                    "passes only if no cracks or scaling are seen.",
    },
    "TEST-0028": {
        "summary": "A second way of expressing how well the insulation resists current "
                    "leakage, normalised per kilometre of cable rather than as a material-"
                    "only property -- used because some limit tables are written in this "
                    "unit instead of volume resistivity.",
        "measurement": "Uses the exact same readings as the Volume Resistivity test above "
                        "(insulation resistance, specimen length, and the two diameters) -- "
                        "no separate measurement is needed.",
        "formula": "Insulation Resistance Constant (MΩ·km) = Specimen Length (m) × Insulation "
                    "Resistance (MΩ) ÷ (1000 × log₁₀(Outer Diameter ÷ Conductor Diameter))\n\n"
                    "A higher result is better -- it must meet or exceed the minimum for this "
                    "insulation type.",
    },
}


def get_procedure_note(test_id: str) -> Optional[ProcedureNote]:
    return PROCEDURE_NOTES.get(test_id)
