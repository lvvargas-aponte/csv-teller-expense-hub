"""Merchant Category Code (ISO 18245) → app category mapping.

SimpleFIN passes the card network's MCC through on transactions that carry
one (``t["mcc"]``). The code is assigned to the *merchant* by its acquiring
bank and rides along with the authorization, so it beats merchant-name
matching outright: "SQ *TRULIANT AMPHITHEA CHARLOTTE NC" reads as noise,
but its 5811 says caterer.

Coverage is uneven, and that's the source's doing rather than a gap here —
of the connected accounts only the Citi card populates ``mcc`` at all,
roughly a quarter of transactions overall. Everything else falls through to
the existing LLM/manual path. That's also why an unmapped code returns
``None`` instead of "Other": ``None`` reads as "still needs a category" to
the rest of the app, while any real label reads as "decided".

Target vocabulary is ``categorizer.DEFAULT_CATEGORIES`` — the axis budgets
and the LLM suggester already share — so anything this module emits is a
bucket the app already understands. Codes with no honest home there are
deliberately left unmapped rather than forced: home/trade contractors
(1711, 1731, ...), tax payments (9311), ATM disbursements (6011), and
card-to-card payments (which arrive as 0000 anyway).

The entity buckets in ``DEFAULT_CATEGORIES`` ("Tomatillo LLC", "Rental: …")
are never auto-assigned — which legal entity a charge belongs to is a fact
about intent that no merchant code can carry.

Judgment calls, grouped here so they're easy to flip:

* **5300 wholesale clubs → Groceries.** Warehouse-club spend is mostly food
  in a household budget. Move to Shopping if you'd rather split it by hand.
* **5921 package/liquor stores → Groceries.** Bought to take home, not
  consumed out; "Dining" would overstate restaurant spend.
* **5813 bars/taverns → Dining.** ``category_normalizer`` blesses a "Drinks"
  label, but it isn't in ``DEFAULT_CATEGORIES``, so bars land with meals.
* **5999 misc/specialty retail → Shopping.** A genuine catch-all that
  acquirers hand out freely; Shopping is the least-wrong home for it.
* **7997 membership clubs → Health.** Gyms commonly bill under it, though
  the code also covers country clubs.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple


# Grouped by the category each code resolves to. Inverted once at import.
_CODES_BY_CATEGORY: Dict[str, Tuple[str, ...]] = {
    "Groceries": (
        "5300",  # Wholesale clubs
        "5411",  # Grocery stores, supermarkets
        "5422",  # Freezer/locker meat provisioners
        "5441",  # Candy, nut, confectionery stores
        "5451",  # Dairy product stores
        "5462",  # Bakeries
        "5499",  # Misc food stores, convenience stores, markets
        "5921",  # Package stores — beer, wine, liquor
    ),
    "Dining": (
        "5811",  # Caterers
        "5812",  # Eating places, restaurants
        "5813",  # Bars, taverns, nightclubs, lounges
        "5814",  # Fast food restaurants
    ),
    "Gas": (
        "5541",  # Service stations
        "5542",  # Automated fuel dispensers
        "5983",  # Fuel dealers — oil, coal, wood, LP
    ),
    "Transport": (
        "4111",  # Local/suburban commuter transport, ferries
        "4112",  # Passenger railways
        "4121",  # Taxicabs, limousines, rideshare
        "4131",  # Bus lines
        "4784",  # Tolls, bridge fees
        "5511",  # Car dealers — new/used
        "5521",  # Car dealers — used only
        "5532",  # Automotive tire stores
        "5533",  # Automotive parts and accessories
        "5561",  # Camper, recreational and utility trailer dealers
        "5571",  # Motorcycle shops and dealers
        "7523",  # Parking lots, garages, meters
        "7531",  # Automotive body repair
        "7534",  # Tire retreading and repair
        "7535",  # Automotive paint shops
        "7538",  # Automotive service shops
        "7542",  # Car washes
        "7549",  # Towing services
    ),
    "Travel": (
        "4411",  # Cruise lines
        "4511",  # Airlines, air carriers
        "4582",  # Airports, airport terminals, flying fields
        "4722",  # Travel agencies and tour operators
        "4723",  # Package tour operators
        "7011",  # Lodging — hotels, motels, resorts
        "7012",  # Timeshares
        "7032",  # Sporting and recreational camps
        "7033",  # Trailer parks and campgrounds
        "7512",  # Automobile rental agencies
        "7513",  # Truck and utility trailer rentals
        "7519",  # Motor home and recreational vehicle rentals
    ),
    "Utilities": (
        "4812",  # Telecommunication equipment, phone sales
        "4814",  # Telecommunication services
        "4816",  # Computer network / information services
        "4899",  # Cable, satellite, other pay TV and radio
        "4900",  # Utilities — electric, gas, water, sanitary
    ),
    "Health": (
        "5047",  # Medical, dental, ophthalmic, hospital equipment
        "5122",  # Drugs, drug proprietors, druggists' sundries
        "5912",  # Drug stores and pharmacies
        "5975",  # Hearing aids — sales, service, supply
        "5976",  # Orthopedic goods, prosthetics
        "7997",  # Membership clubs — gyms, athletic, country clubs
        "8011",  # Doctors and physicians
        "8021",  # Dentists and orthodontists
        "8031",  # Osteopaths
        "8041",  # Chiropractors
        "8042",  # Optometrists and ophthalmologists
        "8043",  # Opticians, eyeglasses
        "8049",  # Podiatrists and chiropodists
        "8050",  # Nursing and personal care facilities
        "8062",  # Hospitals
        "8071",  # Medical and dental laboratories
        "8093",  # Specialty outpatient facilities
        "8099",  # Medical services, health practitioners
    ),
    "Insurance": (
        "5960",  # Direct marketing — insurance services
        "6300",  # Insurance sales, underwriting, premiums
        "6381",  # Insurance premiums
        "6399",  # Insurance, not elsewhere classified
    ),
    "Rent": (
        "6513",  # Real estate agents and managers — rentals
    ),
    "Subscriptions": (
        "5968",  # Direct marketing — continuity/subscription merchants
    ),
    "Entertainment": (
        "5815",  # Digital goods — books, movies, music
        "5816",  # Digital goods — games
        "5817",  # Digital goods — applications (excluding games)
        "5818",  # Digital goods — multi-category
        "7829",  # Motion picture and video tape production/distribution
        "7832",  # Motion picture theaters
        "7841",  # Video tape rental stores
        "7911",  # Dance halls, studios, schools
        "7922",  # Theatrical producers, ticket agencies
        "7929",  # Bands, orchestras, entertainers
        "7932",  # Billiard and pool establishments
        "7933",  # Bowling alleys
        "7941",  # Sports clubs, fields, commercial sports promoters
        "7991",  # Tourist attractions and exhibits
        "7992",  # Public golf courses
        "7993",  # Video amusement game supplies
        "7994",  # Video game arcades and establishments
        "7996",  # Amusement parks, carnivals, circuses
        "7998",  # Aquariums, seaquariums, dolphinariums, zoos
        "7999",  # Recreation services, not elsewhere classified
    ),
    "Shopping": (
        "5200",  # Home supply warehouse stores
        "5211",  # Lumber and building materials
        "5231",  # Glass, paint, wallpaper stores
        "5251",  # Hardware stores
        "5261",  # Nurseries, lawn and garden supply
        "5309",  # Duty free stores
        "5310",  # Discount stores
        "5311",  # Department stores
        "5331",  # Variety stores
        "5399",  # Misc general merchandise
        "5611",  # Men's and boys' clothing and accessories
        "5621",  # Women's ready-to-wear stores
        "5631",  # Women's accessory and specialty shops
        "5641",  # Children's and infants' wear stores
        "5651",  # Family clothing stores
        "5655",  # Sports and riding apparel stores
        "5661",  # Shoe stores
        "5681",  # Furriers and fur shops
        "5691",  # Men's and women's clothing stores
        "5697",  # Tailors, seamstresses, mending, alterations
        "5698",  # Wig and toupee stores
        "5699",  # Misc apparel and accessory shops
        "5712",  # Furniture, home furnishings, equipment
        "5713",  # Floor covering stores
        "5714",  # Drapery, window covering, upholstery stores
        "5718",  # Fireplace, fireplace screens, accessories
        "5719",  # Misc home furnishing specialty stores
        "5722",  # Household appliance stores
        "5732",  # Electronics stores
        "5733",  # Music stores — instruments, sheet music
        "5734",  # Computer software stores
        "5735",  # Record shops
        "5931",  # Used merchandise and secondhand stores
        "5941",  # Sporting goods stores
        "5942",  # Book stores
        "5943",  # Stationery, office and school supply stores
        "5944",  # Jewelry, watch, clock, silverware stores
        "5945",  # Hobby, toy, game shops
        "5946",  # Camera and photographic supply stores
        "5947",  # Gift, card, novelty, souvenir shops
        "5948",  # Luggage and leather goods stores
        "5949",  # Sewing, needlework, fabric, piece goods stores
        "5950",  # Glassware and crystal stores
        "5970",  # Artist supply and craft shops
        "5971",  # Art dealers and galleries
        "5972",  # Stamp and coin stores
        "5977",  # Cosmetic stores
        "5978",  # Typewriter stores
        "5992",  # Florists
        "5993",  # Cigar stores and stands
        "5994",  # News dealers and newsstands
        "5995",  # Pet shops, pet food and supplies
        "5999",  # Misc and specialty retail
    ),
    "Fees": (
        "9222",  # Fines
    ),
}


# Contiguous blocks where the network assigns one code per merchant brand —
# every airline, car-rental agency, and hotel chain has its own. Listing
# them individually would add ~1000 dict entries for no added meaning.
_RANGE_CATEGORIES: Tuple[Tuple[int, int, str], ...] = (
    (3000, 3299, "Travel"),  # Airlines, one code per carrier
    (3300, 3499, "Travel"),  # Car rental agencies
    (3500, 3999, "Travel"),  # Hotels, motels, resorts
)


def _build_lookup() -> Dict[str, str]:
    """Invert ``_CODES_BY_CATEGORY``, refusing to silently drop a duplicate.

    A code listed under two categories is an editing mistake, and the dict
    comprehension would resolve it to whichever came last — so fail loudly
    at import instead of shipping a coin-flip mapping.
    """
    lookup: Dict[str, str] = {}
    for category, codes in _CODES_BY_CATEGORY.items():
        for code in codes:
            if code in lookup:
                raise ValueError(
                    f"MCC {code} mapped to both {lookup[code]!r} and {category!r}"
                )
            lookup[code] = category
    return lookup


_MCC_TO_CATEGORY: Dict[str, str] = _build_lookup()


def category_for_mcc(raw: Optional[str]) -> Optional[str]:
    """Return the app category for an MCC, or ``None`` when it says nothing.

    ``None`` is returned for: missing/blank input, non-numeric junk, codes
    longer than four digits, the all-zero placeholder issuers send when no
    real code applies (every card-payment/autopay row in the current data
    arrives as "0000"), and any valid code this module doesn't map.

    Short codes are left-padded — issuers inconsistently drop leading zeros,
    so "711" and "0711" are the same trade-contractor code.
    """
    if raw is None:
        return None
    code = str(raw).strip()
    if not code or not code.isdigit() or len(code) > 4:
        return None
    code = code.zfill(4)
    if code == "0000":
        return None

    hit = _MCC_TO_CATEGORY.get(code)
    if hit:
        return hit

    numeric = int(code)
    for low, high, category in _RANGE_CATEGORIES:
        if low <= numeric <= high:
            return category
    return None
