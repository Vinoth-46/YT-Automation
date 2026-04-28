"""
╔══════════════════════════════════════════════════════════════════════╗
║     VEO 2 — AI FOOTAGE PROMPTS (All 30 Topics)                      ║
║     Tamil Civil Engineering YouTube Shorts Pipeline                  ║
║     Model : veo-2.0-generate-001  |  Aspect : 9:16  |  Duration: 8s ║
╚══════════════════════════════════════════════════════════════════════╝

HOW TO USE:
───────────
In your step2_generate_footage.py, call:

    operation = client.models.generate_videos(
        model="veo-2.0-generate-001",
        prompt=VEO_PROMPTS[script_id],   # use the prompt for that script
        config=genai.types.GenerateVideoConfig(
            aspect_ratio="9:16",
            duration_seconds=8,
            number_of_videos=1,
        ),
    )

GLOBAL STYLE SUFFIX (automatically appended to all prompts in code):
─────────────────────────────────────────────────────────────────────
"cinematic vertical portrait video, 9:16 aspect ratio, realistic Tamil Nadu
construction site, natural golden hour or bright daylight, shot on DSLR camera,
shallow depth of field, photorealistic, no text, no watermarks, no CGI"


══════════════════════════════════════════════════════════════════════
SCRIPT 01 — Concrete Mix Ratio
══════════════════════════════════════════════════════════════════════
A construction worker at a Tamil Nadu building site scooping and mixing cement,
river sand, and granite aggregate on a steel plate in a 1:1.5:3 ratio, close-up
of hands working the dry mix, then water being added slowly and mixed to a
smooth grey paste, concrete consistency being tested by lifting a handful,
dusty boots and a partially built brick wall in the background


══════════════════════════════════════════════════════════════════════
SCRIPT 02 — Foundation Types
══════════════════════════════════════════════════════════════════════
Deep rectangular trench excavated in red laterite soil at a house construction
site in Tamil Nadu, two workers inside the trench laying a bed of rubble stone
with cement mortar, another worker on the surface guiding a plumb bob to check
alignment, excavated soil piled on the side, early morning light casting long
shadows across the site


══════════════════════════════════════════════════════════════════════
SCRIPT 03 — Rebar Spacing Rules
══════════════════════════════════════════════════════════════════════
Close-up of a TMT steel rebar grid being tied with binding wire on a
construction site floor, worker crouching and wrapping wire at each intersection
with a hook tool, measuring tape laid alongside showing 150mm spacing between
bars, steel rods gleaming in bright sunlight, concrete columns and walls
partially visible in the background


══════════════════════════════════════════════════════════════════════
SCRIPT 04 — Brick Bonding Patterns
══════════════════════════════════════════════════════════════════════
Skilled mason's hands spreading grey cement mortar on a course of red clay
bricks using a trowel, then placing the next brick in English bond pattern,
tapping it level with the rubber mallet, excess mortar squeezed out being
scraped clean, the rising brick wall perfectly plumb and straight, a spirit
level resting on top, warm afternoon light on the wall texture


══════════════════════════════════════════════════════════════════════
SCRIPT 05 — Plinth Beam Importance
══════════════════════════════════════════════════════════════════════
Concrete plinth beam being poured around the entire ground perimeter of a
new house, wooden plank shuttering held in place by props, a worker guiding
wet concrete from a mixer down a chute into the formwork, another using a
vibrator rod to eliminate air pockets, the beam level with the ground around
it, brick wall stub columns visible above


══════════════════════════════════════════════════════════════════════
SCRIPT 06 — Lintel vs Beam
══════════════════════════════════════════════════════════════════════
Close-up view looking up at a concrete lintel being cast above a window
opening in a brick wall, rebar cage visible inside the thin formwork, worker
pouring concrete from a bucket carefully into the narrow mould, another worker
holding the formwork steady, bright sky visible through the unglazed window
opening below, scaffolding on the wall exterior


══════════════════════════════════════════════════════════════════════
SCRIPT 07 — BBS Calculation
══════════════════════════════════════════════════════════════════════
Civil engineer in a safety helmet and yellow vest standing at a site office
table reviewing a bar bending schedule drawing, finger tracing the rod
dimensions and cut lengths, workers in the background using an angle grinder
to cut TMT bars to exact measured lengths, sparks flying, steel bar bundles
stacked neatly on the ground beside them


══════════════════════════════════════════════════════════════════════
SCRIPT 08 — Shuttering Removal Timing
══════════════════════════════════════════════════════════════════════
Two workers carefully prying wooden shuttering planks away from a cured
concrete column using crowbars, the smooth grey concrete surface being
revealed underneath, small wooden wedges being tapped loose, a third worker
collecting the removed planks and stacking them, mid-morning light, concrete
column showing a perfect finish with only faint formwork joint lines


══════════════════════════════════════════════════════════════════════
SCRIPT 09 — Water Cement Ratio
══════════════════════════════════════════════════════════════════════
Extreme close-up of a worker measuring water in a marked plastic bucket then
carefully pouring it in a thin controlled stream into a concrete mix on a
steel plate, the mix changing consistency as water is added, hand testing
the slump by lifting a handful and watching it fall, a cement bag and sand
pile visible beside the mixing area, hot midday light


══════════════════════════════════════════════════════════════════════
SCRIPT 10 — Curing Period
══════════════════════════════════════════════════════════════════════
Worker walking slowly across a newly cast flat roof slab, dragging a garden
hose and spraying a steady mist of water over the entire grey concrete surface,
water beading and pooling in the texture, close-up of wet burlap hessian cloth
being pressed flat over the damp surface, another shot of water-cured walls
with dark wet patches, early morning golden light, steam rising faintly


══════════════════════════════════════════════════════════════════════
SCRIPT 11 — Soil Bearing Capacity
══════════════════════════════════════════════════════════════════════
Soil investigation at a vacant plot in Tamil Nadu, a worker operating a manual
borehole drilling rig pushing into the ground, pulling up a soil sample tube
packed with red clay, a civil engineer in hard hat crouching to examine the
sample and note colour and texture, shallow borehole open beside him with
soil layers visible, rural site with trees in the background


══════════════════════════════════════════════════════════════════════
SCRIPT 12 — Column Design Basics
══════════════════════════════════════════════════════════════════════
Three stages of a concrete column in one scene: on the left a finished rebar
cage with stirrups tied at regular intervals standing upright, in the middle
wooden box formwork assembled around a rebar cage, on the right a completed
de-shuttered concrete column with a smooth grey surface, workers moving between
the stages in the background, construction site setting


══════════════════════════════════════════════════════════════════════
SCRIPT 13 — Retaining Wall Construction
══════════════════════════════════════════════════════════════════════
Stone masonry retaining wall being built on a steeply sloped site, worker
lifting a large dressed granite stone and setting it in mortar, wall already
three courses high with weep holes left at the base using PVC pipe offcuts,
terraced soil held back behind, a coconut tree and green hillside behind the
wall, afternoon shadows across the stone face


══════════════════════════════════════════════════════════════════════
SCRIPT 14 — Slab Thickness
══════════════════════════════════════════════════════════════════════
Worker laying and tying rebar mesh flat for a roof slab, a civil engineer
kneeling beside the mesh pushing a ruler down through the mesh to measure
the cover block height below it, confirming slab thickness, another angle
showing concrete mixer truck pouring concrete onto the mesh as workers spread
it with rakes and shovels, the slab surface being levelled with a screed board


══════════════════════════════════════════════════════════════════════
SCRIPT 15 — Staircase Design
══════════════════════════════════════════════════════════════════════
Concrete staircase under construction inside a building shell, rebar
framework for each tread and riser visible inside angled formwork, a worker
pouring concrete from a bucket step by step into the mould, another worker
using a small vibrator to compact each step, the lower finished steps already
de-shuttered and smooth, overhead light through an open roof


══════════════════════════════════════════════════════════════════════
SCRIPT 16 — DPC Layer
══════════════════════════════════════════════════════════════════════
Worker kneeling at the top of a foundation wall brushing thick black bitumen
waterproofing compound onto the horizontal surface before brick wall
construction begins, the shiny black DPC layer contrasting against the grey
concrete below, another angle showing a thin polythene sheet DPC being rolled
out and pressed flat over a fresh cement screed layer, trowel smoothing it


══════════════════════════════════════════════════════════════════════
SCRIPT 17 — Building Approval Steps
══════════════════════════════════════════════════════════════════════
Civil engineer and property owner sitting across a desk at a panchayat or
municipality office in Tamil Nadu, spreading out a building plan drawing on
the table, an officer reviewing the plan and stamping a document, exterior
shot of the local government office building with people entering, then back
to the site where an approved plan is pinned to a board at the construction
site entrance


══════════════════════════════════════════════════════════════════════
SCRIPT 18 — Bank Estimate Tips
══════════════════════════════════════════════════════════════════════
Civil engineer at a desk in a site office, working on a detailed cost
estimate spreadsheet on a laptop, construction drawings unrolled beside the
laptop, a calculator and pen in hand, pages of a bill of quantities visible,
close-up of the screen showing line items for cement, steel, labour costs,
stacks of material rate charts on the desk


══════════════════════════════════════════════════════════════════════
SCRIPT 19 — FSI and FAR Rules
══════════════════════════════════════════════════════════════════════
Architect standing at a site boundary with a measuring tape, surveying the
plot dimensions, building plan held in one hand with the permitted floor area
highlighted, wide shot of an urban Tamil Nadu street with multi-storey buildings
under construction at various heights, crane visible, then close-up of a plan
showing plot outline and building footprint drawn within the setback lines


══════════════════════════════════════════════════════════════════════
SCRIPT 20 — Vastu Basics
══════════════════════════════════════════════════════════════════════
Traditional ground-breaking ceremony at a house construction site in Tamil Nadu,
a small clay lamp burning at the northeast corner of the plot, flowers and
turmeric on the soil, family members gathered, a compass being held over the
site plan to check cardinal directions, then workers beginning to mark the
foundation layout with lime powder along the direction lines


══════════════════════════════════════════════════════════════════════
SCRIPT 21 — Rainwater Harvesting
══════════════════════════════════════════════════════════════════════
Worker fitting a PVC downpipe from a rooftop gutter that channels rainwater
down to a filter chamber at ground level built of brick and filled with gravel
and charcoal layers, another worker digging a trench beside the house for a
perforated PVC pipe leading to a recharge pit, cross-section of the gravel
filter visible, light rain falling creating ripples in a water storage sump


══════════════════════════════════════════════════════════════════════
SCRIPT 22 — Earthquake Resistant Design
══════════════════════════════════════════════════════════════════════
Close-up of ductile TMT rebar connections at a beam-column joint being tied
with extra stirrups closely spaced in the confinement zone, a civil engineer
marking the stirrup spacing on the rebar with chalk, wide shot of a reinforced
concrete frame building under construction showing shear walls being poured,
workers placing concrete carefully around the dense reinforcement


══════════════════════════════════════════════════════════════════════
SCRIPT 23 — Plumbing Layout
══════════════════════════════════════════════════════════════════════
Plumber working inside a partially built house, routing orange PVC pipes
along the floor and up the wall for the kitchen and bathroom, using solvent
cement to join pipe fittings, pipes temporarily propped in position before
walls are plastered over them, a second angle showing pipes embedded in a
wall chase cut with a grinder, dust in the air, measuring tape in use


══════════════════════════════════════════════════════════════════════
SCRIPT 24 — Electrical Conduit in Slab
══════════════════════════════════════════════════════════════════════
Electrician lying the grey PVC conduit pipes flat across a rebar mesh roof
slab before concreting, bending flexible conduit around corners, fixing pipes
to the rebar with wire ties, junction boxes pressed into position at future
light point locations, a second worker carefully routing the conduit path
between the rebar, close-up of the conduit being tied at 300mm intervals


══════════════════════════════════════════════════════════════════════
SCRIPT 25 — Paint Selection Guide
══════════════════════════════════════════════════════════════════════
Painter applying interior emulsion paint with a roller on a freshly plastered
white wall, smooth even strokes, close-up of the roller texture leaving a
slight texture, then an exterior wall being painted with a brush, texture
paint being applied creating a pebbled surface, paint shade cards fanned out
being compared against a wall in warm natural light, several paint tins open


══════════════════════════════════════════════════════════════════════
SCRIPT 26 — Tile vs Marble
══════════════════════════════════════════════════════════════════════
Split floor scene: on one side a tiler laying large format vitrified ceramic
tiles using grey adhesive and plastic spacers, tapping level with a rubber
mallet, on the other side a marble slab being carefully lowered onto a white
cement bed by two workers and aligned, close-up comparison of both surfaces
side by side showing texture differences in bright light, grouting being
applied to tile joints


══════════════════════════════════════════════════════════════════════
SCRIPT 27 — Wood vs uPVC Windows
══════════════════════════════════════════════════════════════════════
Side by side window installation in adjacent wall openings: a carpenter
fitting a teak wood frame into one opening using wooden wedges and a level,
chiselling and planing the frame fit, while beside it a white uPVC window
frame is being set into the second opening with expanding foam sealant, both
windows being checked for plumb and square, finished exteriors of both visible


══════════════════════════════════════════════════════════════════════
SCRIPT 28 — Solar Panel on Roof
══════════════════════════════════════════════════════════════════════
Two workers in safety harness on a flat concrete rooftop in Tamil Nadu,
assembling aluminium mounting rails on pre-drilled anchor bolts, lifting a
solar panel and sliding it onto the rails, connecting black DC cables between
panels with MC4 connectors, wide shot of a completed array of 8 panels
gleaming in bright midday sun, an inverter box being mounted on a wall below


══════════════════════════════════════════════════════════════════════
SCRIPT 29 — Construction Cost Estimation
══════════════════════════════════════════════════════════════════════
Civil engineer walking through a construction site with a clipboard, stopping
to measure wall lengths with a tape measure and note dimensions, checking
ceiling height, counting number of columns, then sitting at a site office
table opening a laptop showing a spreadsheet with cost line items, stacks of
construction material catalogues and rate lists spread on the table beside him


══════════════════════════════════════════════════════════════════════
SCRIPT 30 — Top 5 Construction Mistakes
══════════════════════════════════════════════════════════════════════
Five distinct close-up defect shots in rapid sequence: (1) a long diagonal
crack running across plastered wall surface, (2) a dark water seepage stain
spreading from a corner ceiling, (3) uneven floor tiles with visible height
difference between two tiles, (4) concrete column with exposed rusted rebar
visible through spalled surface, (5) a poorly finished concrete beam with
honeycomb voids showing aggregate, each shot dramatic and close, harsh light
"""

# ══════════════════════════════════════════════════════════════════════
# PYTHON DICT — paste directly into step2_generate_footage.py
# ══════════════════════════════════════════════════════════════════════

GLOBAL_SUFFIX = (
    ", cinematic vertical portrait video, 9:16 aspect ratio, "
    "realistic Tamil Nadu construction site, natural golden hour or "
    "bright daylight, shot on DSLR camera, shallow depth of field, "
    "photorealistic, no text, no watermarks, no CGI"
)

VEO_PROMPTS = {
    1: "A construction worker at a Tamil Nadu building site scooping and mixing cement, river sand, and granite aggregate on a steel plate in a 1:1.5:3 ratio, close-up of hands working the dry mix, then water being added slowly and mixed to a smooth grey paste, concrete consistency being tested by lifting a handful, dusty boots and a partially built brick wall in the background",
    2: "Deep rectangular trench excavated in red laterite soil at a house construction site in Tamil Nadu, two workers inside the trench laying a bed of rubble stone with cement mortar, another worker on the surface guiding a plumb bob to check alignment, excavated soil piled on the side, early morning light casting long shadows across the site",
    3: "Close-up of a TMT steel rebar grid being tied with binding wire on a construction site floor, worker crouching and wrapping wire at each intersection with a hook tool, measuring tape laid alongside showing 150mm spacing between bars, steel rods gleaming in bright sunlight, concrete columns and walls partially visible in the background",
    4: "Skilled mason's hands spreading grey cement mortar on a course of red clay bricks using a trowel, then placing the next brick in English bond pattern, tapping it level with the rubber mallet, excess mortar squeezed out being scraped clean, the rising brick wall perfectly plumb and straight, a spirit level resting on top, warm afternoon light on the wall texture",
    5: "Concrete plinth beam being poured around the entire ground perimeter of a new house, wooden plank shuttering held in place by props, a worker guiding wet concrete from a mixer down a chute into the formwork, another using a vibrator rod to eliminate air pockets, the beam level with the ground around it, brick wall stub columns visible above",
    6: "Close-up view looking up at a concrete lintel being cast above a window opening in a brick wall, rebar cage visible inside the thin formwork, worker pouring concrete from a bucket carefully into the narrow mould, another worker holding the formwork steady, bright sky visible through the unglazed window opening below, scaffolding on the wall exterior",
    7: "Civil engineer in a safety helmet and yellow vest standing at a site office table reviewing a bar bending schedule drawing, finger tracing the rod dimensions and cut lengths, workers in the background using an angle grinder to cut TMT bars to exact measured lengths, sparks flying, steel bar bundles stacked neatly on the ground beside them",
    8: "Two workers carefully prying wooden shuttering planks away from a cured concrete column using crowbars, the smooth grey concrete surface being revealed underneath, small wooden wedges being tapped loose, a third worker collecting the removed planks and stacking them, mid-morning light, concrete column showing a perfect finish with only faint formwork joint lines",
    9: "Extreme close-up of a worker measuring water in a marked plastic bucket then carefully pouring it in a thin controlled stream into a concrete mix on a steel plate, the mix changing consistency as water is added, hand testing the slump by lifting a handful and watching it fall, a cement bag and sand pile visible beside the mixing area, hot midday light",
    10: "Worker walking slowly across a newly cast flat roof slab, dragging a garden hose and spraying a steady mist of water over the entire grey concrete surface, water beading and pooling in the texture, close-up of wet burlap hessian cloth being pressed flat over the damp surface, another shot of water-cured walls with dark wet patches, early morning golden light, steam rising faintly",
    11: "Soil investigation at a vacant plot in Tamil Nadu, a worker operating a manual borehole drilling rig pushing into the ground, pulling up a soil sample tube packed with red clay, a civil engineer in hard hat crouching to examine the sample and note colour and texture, shallow borehole open beside him with soil layers visible, rural site with trees in the background",
    12: "Three stages of a concrete column in one scene: on the left a finished rebar cage with stirrups tied at regular intervals standing upright, in the middle wooden box formwork assembled around a rebar cage, on the right a completed de-shuttered concrete column with a smooth grey surface, workers moving between the stages in the background, construction site setting",
    13: "Stone masonry retaining wall being built on a steeply sloped site, worker lifting a large dressed granite stone and setting it in mortar, wall already three courses high with weep holes left at the base using PVC pipe offcuts, terraced soil held back behind, a coconut tree and green hillside behind the wall, afternoon shadows across the stone face",
    14: "Worker laying and tying rebar mesh flat for a roof slab, a civil engineer kneeling beside the mesh pushing a ruler down through the mesh to measure the cover block height below it, confirming slab thickness, another angle showing concrete mixer truck pouring concrete onto the mesh as workers spread it with rakes and shovels, the slab surface being levelled with a screed board",
    15: "Concrete staircase under construction inside a building shell, rebar framework for each tread and riser visible inside angled formwork, a worker pouring concrete from a bucket step by step into the mould, another worker using a small vibrator to compact each step, the lower finished steps already de-shuttered and smooth, overhead light through an open roof",
    16: "Worker kneeling at the top of a foundation wall brushing thick black bitumen waterproofing compound onto the horizontal surface before brick wall construction begins, the shiny black DPC layer contrasting against the grey concrete below, another angle showing a thin polythene sheet DPC being rolled out and pressed flat over a fresh cement screed layer, trowel smoothing it",
    17: "Civil engineer and property owner sitting across a desk at a panchayat or municipality office in Tamil Nadu, spreading out a building plan drawing on the table, an officer reviewing the plan and stamping a document, exterior shot of the local government office building with people entering, then back to the site where an approved plan is pinned to a board at the construction site entrance",
    18: "Civil engineer at a desk in a site office, working on a detailed cost estimate spreadsheet on a laptop, construction drawings unrolled beside the laptop, a calculator and pen in hand, pages of a bill of quantities visible, close-up of the screen showing line items for cement, steel, labour costs, stacks of material rate charts on the desk",
    19: "Architect standing at a site boundary with a measuring tape, surveying the plot dimensions, building plan held in one hand with the permitted floor area highlighted, wide shot of an urban Tamil Nadu street with multi-storey buildings under construction at various heights, crane visible, then close-up of a plan showing plot outline and building footprint drawn within the setback lines",
    20: "Traditional ground-breaking ceremony at a house construction site in Tamil Nadu, a small clay lamp burning at the northeast corner of the plot, flowers and turmeric on the soil, family members gathered, a compass being held over the site plan to check cardinal directions, then workers beginning to mark the foundation layout with lime powder along the direction lines",
    21: "Worker fitting a PVC downpipe from a rooftop gutter that channels rainwater down to a filter chamber at ground level built of brick and filled with gravel and charcoal layers, another worker digging a trench beside the house for a perforated PVC pipe leading to a recharge pit, cross-section of the gravel filter visible, light rain falling creating ripples in a water storage sump",
    22: "Close-up of ductile TMT rebar connections at a beam-column joint being tied with extra stirrups closely spaced in the confinement zone, a civil engineer marking the stirrup spacing on the rebar with chalk, wide shot of a reinforced concrete frame building under construction showing shear walls being poured, workers placing concrete carefully around the dense reinforcement",
    23: "Plumber working inside a partially built house, routing orange PVC pipes along the floor and up the wall for the kitchen and bathroom, using solvent cement to join pipe fittings, pipes temporarily propped in position before walls are plastered over them, a second angle showing pipes embedded in a wall chase cut with a grinder, dust in the air, measuring tape in use",
    24: "Electrician lying the grey PVC conduit pipes flat across a rebar mesh roof slab before concreting, bending flexible conduit around corners, fixing pipes to the rebar with wire ties, junction boxes pressed into position at future light point locations, a second worker carefully routing the conduit path between the rebar, close-up of the conduit being tied at 300mm intervals",
    25: "Painter applying interior emulsion paint with a roller on a freshly plastered white wall, smooth even strokes, close-up of the roller texture leaving a slight texture, then an exterior wall being painted with a brush, texture paint being applied creating a pebbled surface, paint shade cards fanned out being compared against a wall in warm natural light, several paint tins open",
    26: "Split floor scene: on one side a tiler laying large format vitrified ceramic tiles using grey adhesive and plastic spacers, tapping level with a rubber mallet, on the other side a marble slab being carefully lowered onto a white cement bed by two workers and aligned, close-up comparison of both surfaces side by side showing texture differences in bright light, grouting being applied to tile joints",
    27: "Side by side window installation in adjacent wall openings: a carpenter fitting a teak wood frame into one opening using wooden wedges and a level, chiselling and planing the frame fit, while beside it a white uPVC window frame is being set into the second opening with expanding foam sealant, both windows being checked for plumb and square, finished exteriors of both visible",
    28: "Two workers in safety harness on a flat concrete rooftop in Tamil Nadu, assembling aluminium mounting rails on pre-drilled anchor bolts, lifting a solar panel and sliding it onto the rails, connecting black DC cables between panels with MC4 connectors, wide shot of a completed array of 8 panels gleaming in bright midday sun, an inverter box being mounted on a wall below",
    29: "Civil engineer walking through a construction site with a clipboard, stopping to measure wall lengths with a tape measure and note dimensions, checking ceiling height, counting number of columns, then sitting at a site office table opening a laptop showing a spreadsheet with cost line items, stacks of construction material catalogues and rate lists spread on the table beside him",
    30: "Five distinct close-up defect shots in rapid sequence: a long diagonal crack running across a plastered wall surface, a dark water seepage stain spreading from a corner ceiling, uneven floor tiles with visible height difference, a concrete column with exposed rusted rebar visible through spalled surface, a poorly finished concrete beam with honeycomb voids showing aggregate, each shot dramatic and close with harsh light",
}


def get_prompt(script_id: int) -> str:
    """Get the full VEO 2 prompt for a given script ID (1-30), with global suffix appended."""
    if script_id not in VEO_PROMPTS:
        raise ValueError(f"Script ID {script_id} not found. Valid range: 1-30.")
    return VEO_PROMPTS[script_id] + GLOBAL_SUFFIX


if __name__ == "__main__":
    # Preview all prompts
    for sid in sorted(VEO_PROMPTS):
        print(f"\n{'═' * 70}")
        print(f"  SCRIPT {sid:02d}")
        print(f"{'═' * 70}")
        print(get_prompt(sid))
    print(f"\n\nTotal prompts: {len(VEO_PROMPTS)}")
