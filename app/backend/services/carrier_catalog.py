"""Deterministic expanded carrier catalog for the carrier search agent."""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.backend.core.domain_enums import CarrierPricingModel


@dataclass(frozen=True)
class CanonicalCarrier:
    id: UUID
    company_name: str
    truck_type_id: int | None
    reliability_rating: Decimal
    documentation_valid: bool
    adr_capable: bool
    base_price_km: Decimal
    home_base_text: str
    service_countries: list[str]
    preferred_lanes: list[str]
    pricing_model: CarrierPricingModel
    flat_rate_amount: Decimal | None
    fuel_surcharge_pct: Decimal | None


def _p(uid: str, name: str, tt: int | None, rel: str, doc: bool, adr: bool, price: str,
       base: str, countries: list[str], lanes: list[str],
       pm: CarrierPricingModel = CarrierPricingModel.PER_KM,
       flat: str | None = None, fuel: str | None = None) -> CanonicalCarrier:
    return CanonicalCarrier(
        id=UUID(uid), company_name=name, truck_type_id=tt,
        reliability_rating=Decimal(rel), documentation_valid=doc, adr_capable=adr,
        base_price_km=Decimal(price), home_base_text=base,
        service_countries=countries, preferred_lanes=lanes,
        pricing_model=pm, flat_rate_amount=Decimal(flat) if flat else None,
        fuel_surcharge_pct=Decimal(fuel) if fuel else None,
    )


CANONICAL_CARRIERS: tuple[CanonicalCarrier, ...] = (
    # Original 15 (with new fields added)
    _p("00000000-0000-0000-0000-000000000001", "Atlas Freight SL", 1, "9.60", True, True, "0.7800",
       "Madrid, ES", ["ES", "FR", "PT", "DE"], ["ES->FR", "ES->DE", "PT->ES"]),
    _p("00000000-0000-0000-0000-000000000002", "Boreal Cargo", 1, "8.80", True, False, "0.8200",
       "Helsinki, FI", ["FI", "SE", "NO", "DE"], ["FI->DE", "SE->FI"]),
    _p("00000000-0000-0000-0000-000000000003", "Costa Reefer Lines", 2, "9.10", True, False, "0.9500",
       "Barcelona, ES", ["ES", "IT", "FR", "PT"], ["ES->IT", "ES->FR"]),
    _p("00000000-0000-0000-0000-000000000004", "Delta ADR Movers", None, "7.40", True, True, "0.8800",
       "Rotterdam, NL", ["NL", "DE", "BE", "FR"], ["NL->DE", "NL->FR"]),
    _p("00000000-0000-0000-0000-000000000005", "Epsilon Transit", 3, "8.30", True, True, "1.0500",
       "Munich, DE", ["DE", "AT", "CH", "IT"], ["DE->IT", "DE->AT"]),
    _p("00000000-0000-0000-0000-000000000006", "Faro Logistics", None, "6.20", True, False, "0.9200",
       "Lisbon, PT", ["PT", "ES"], ["PT->ES"]),
    _p("00000000-0000-0000-0000-000000000007", "Galia Trucks", 1, "5.90", True, False, "0.9800",
       "Lyon, FR", ["FR", "ES", "IT", "BE"], ["FR->ES", "FR->IT"]),
    _p("00000000-0000-0000-0000-000000000008", "Helix Transport", 2, "8.50", False, True, "0.8400",
       "Hamburg, DE", ["DE", "NL", "PL", "CZ"], ["DE->PL", "DE->NL"]),
    _p("00000000-0000-0000-0000-000000000009", "Iberic Cargo Net", None, "7.10", False, False, "0.7900",
       "Valencia, ES", ["ES", "PT"], ["ES->PT"]),
    _p("00000000-0000-0000-0000-000000000010", "Jano Fleet", 3, "9.40", True, True, "1.1800",
       "Milan, IT", ["IT", "DE", "FR", "AT"], ["IT->DE", "IT->FR"]),
    _p("00000000-0000-0000-0000-000000000011", "Kappa Road", None, "4.80", True, False, "1.0800",
       "Warsaw, PL", ["PL", "DE", "CZ", "SK"], ["PL->DE"]),
    _p("00000000-0000-0000-0000-000000000012", "Levante Cargo", 1, "7.90", True, True, "0.9100",
       "Zaragoza, ES", ["ES", "FR", "IT"], ["ES->FR", "ES->IT"]),
    _p("00000000-0000-0000-0000-000000000013", "Mistral Freight", 2, "8.00", True, False, "1.1200",
       "Marseille, FR", ["FR", "ES", "IT", "DE"], ["FR->ES", "FR->DE"]),
    _p("00000000-0000-0000-0000-000000000014", "Nexo Carrier Group", None, "9.00", True, True, "0.8700",
       "Brussels, BE", ["BE", "NL", "FR", "DE", "LU"], ["BE->FR", "BE->DE"]),
    _p("00000000-0000-0000-0000-000000000015", "Orion Bulk", 3, "6.80", True, False, "1.3000",
       "Vienna, AT", ["AT", "DE", "HU", "CZ", "IT"], ["AT->DE", "AT->IT"]),
    # New carriers 16-50
    _p("00000000-0000-0000-0000-000000000016", "Pyrenees Express", 1, "8.70", True, False, "0.8500",
       "Toulouse, FR", ["FR", "ES"], ["FR->ES", "ES->FR"]),
    _p("00000000-0000-0000-0000-000000000017", "Nordic Shield Logistics", 2, "9.20", True, True, "0.9600",
       "Stockholm, SE", ["SE", "NO", "FI", "DK"], ["SE->NO", "SE->FI"]),
    _p("00000000-0000-0000-0000-000000000018", "Adriatic Haulers", None, "7.60", True, False, "0.8900",
       "Zagreb, HR", ["HR", "SI", "IT", "AT"], ["HR->IT", "HR->AT"]),
    _p("00000000-0000-0000-0000-000000000019", "Baltic Freight Alliance", 1, "8.10", True, True, "0.9300",
       "Riga, LV", ["LV", "LT", "EE", "PL", "FI"], ["LV->PL", "LV->FI"]),
    _p("00000000-0000-0000-0000-000000000020", "Iberian Peninsula Carriers", 3, "7.80", True, False, "0.8100",
       "Seville, ES", ["ES", "PT", "GI"], ["ES->PT"]),
    _p("00000000-0000-0000-0000-000000000021", "Rhine Valley Transport", 2, "9.30", True, True, "0.9100",
       "Cologne, DE", ["DE", "NL", "BE", "FR"], ["DE->NL", "DE->FR"]),
    _p("00000000-0000-0000-0000-000000000022", "Mediterranean Link", None, "8.40", True, False, "1.0200",
       "Naples, IT", ["IT", "ES", "FR", "GR", "MT"], ["IT->ES", "IT->GR"]),
    _p("00000000-0000-0000-0000-000000000023", "Central European Express", 1, "8.90", True, True, "0.8700",
       "Prague, CZ", ["CZ", "DE", "AT", "PL", "SK"], ["CZ->DE", "CZ->AT"]),
    _p("00000000-0000-0000-0000-000000000024", "Scandinavian Cold Chain", 2, "9.50", True, False, "1.1500",
       "Oslo, NO", ["NO", "SE", "DK", "FI"], ["NO->SE", "NO->DK"]),
    _p("00000000-0000-0000-0000-000000000025", "Danube Logistics Group", 3, "7.20", True, True, "0.9400",
       "Budapest, HU", ["HU", "AT", "SK", "RO", "HR"], ["HU->AT", "HU->RO"]),
    _p("00000000-0000-0000-0000-000000000026", "Atlantic Seaboard Transport", None, "6.90", True, False, "0.9900",
       "Bordeaux, FR", ["FR", "ES", "PT"], ["FR->ES", "FR->PT"]),
    _p("00000000-0000-0000-0000-000000000027", "Benelux Priority Freight", 1, "9.10", True, True, "0.8300",
       "Amsterdam, NL", ["NL", "BE", "LU", "DE", "FR"], ["NL->DE", "NL->FR"]),
    _p("00000000-0000-0000-0000-000000000028", "Balkan Bridge Carriers", 3, "6.50", True, False, "1.0700",
       "Bucharest, RO", ["RO", "BG", "HU", "RS", "MD"], ["RO->HU", "RO->BG"]),
    _p("00000000-0000-0000-0000-000000000029", "Channel Crossing Hauliers", 1, "8.80", True, True, "0.9200",
       "Calais, FR", ["FR", "GB", "BE"], ["FR->GB", "GB->FR"]),
    _p("00000000-0000-0000-0000-000000000030", "Polish Eagle Transport", 2, "7.70", True, False, "0.7800",
       "Krakow, PL", ["PL", "DE", "CZ", "SK", "UA"], ["PL->DE", "PL->CZ"]),
    _p("00000000-0000-0000-0000-000000000031", "Greek Isles Logistics", None, "6.80", True, False, "1.2500",
       "Athens, GR", ["GR", "IT", "BG", "AL"], ["GR->IT"]),
    _p("00000000-0000-0000-0000-000000000032", "Swiss Precision Carriers", 1, "9.80", True, True, "1.3500",
       "Zurich, CH", ["CH", "DE", "AT", "IT", "FR"], ["CH->DE", "CH->IT"]),
    _p("00000000-0000-0000-0000-000000000033", "Portuguese Atlantic Express", 3, "7.50", True, False, "0.8600",
       "Porto, PT", ["PT", "ES"], ["PT->ES", "ES->PT"]),
    _p("00000000-0000-0000-0000-000000000034", "Turkish Straits Transport", None, "5.80", True, True, "0.7200",
       "Istanbul, TR", ["TR", "BG", "GR", "RO"], ["TR->BG", "TR->GR"]),
    _p("00000000-0000-0000-0000-000000000035", "Irish Sea Freight", 2, "8.20", True, False, "1.0800",
       "Dublin, IE", ["IE", "GB"], ["IE->GB", "GB->IE"]),
    _p("00000000-0000-0000-0000-000000000036", "Nordic Light Haulers", 1, "8.60", True, True, "0.9700",
       "Copenhagen, DK", ["DK", "SE", "DE", "NO"], ["DK->DE", "DK->SE"]),
    _p("00000000-0000-0000-0000-000000000037", "Carpathian Cargo", 3, "6.40", True, False, "0.8100",
       "Cluj-Napoca, RO", ["RO", "HU", "UA", "MD"], ["RO->HU"]),
    _p("00000000-0000-0000-0000-000000000038", "Benelux Bulk Carriers", None, "7.90", True, True, "0.9500",
       "Antwerp, BE", ["BE", "NL", "LU", "DE", "FR"], ["BE->DE", "BE->FR"]),
    _p("00000000-0000-0000-0000-000000000039", "Andalusian Express", 1, "7.30", True, False, "0.8400",
       "Malaga, ES", ["ES", "PT", "GI"], ["ES->PT"]),
    _p("00000000-0000-0000-0000-000000000040", "Baltic Amber Transport", 2, "8.00", True, True, "0.9000",
       "Vilnius, LT", ["LT", "LV", "PL", "DE"], ["LT->PL", "LT->DE"]),
    _p("00000000-0000-0000-0000-000000000041", "Provence Premium Freight", 1, "9.00", True, False, "1.1000",
       "Nice, FR", ["FR", "IT", "MC"], ["FR->IT"]),
    _p("00000000-0000-0000-0000-000000000042", "Scandinavian Steel Haulers", 3, "8.50", True, True, "1.2000",
       "Gothenburg, SE", ["SE", "NO", "DK", "DE"], ["SE->DE", "SE->NO"]),
    _p("00000000-0000-0000-0000-000000000043", "Adriatic Coastal Lines", None, "7.10", True, False, "0.9800",
       "Split, HR", ["HR", "IT", "SI", "ME"], ["HR->IT"]),
    _p("00000000-0000-0000-0000-000000000044", "North Sea Connect", 2, "8.90", True, True, "0.9300",
       "Aberdeen, GB", ["GB", "NO", "NL", "DK"], ["GB->NO", "GB->NL"]),
    _p("00000000-0000-0000-0000-000000000045", "Iberian Mountain Express", 1, "7.60", True, False, "0.8800",
       "Bilbao, ES", ["ES", "FR"], ["ES->FR"]),
    _p("00000000-0000-0000-0000-000000000046", "Eastern Alliance Logistics", 3, "6.70", True, True, "0.7600",
       "Sofia, BG", ["BG", "RO", "RS", "GR", "TR"], ["BG->RO", "BG->GR"]),
    _p("00000000-0000-0000-0000-000000000047", "Loire Valley Carriers", None, "8.30", True, False, "1.0400",
       "Nantes, FR", ["FR", "BE", "NL"], ["FR->BE"]),
    _p("00000000-0000-0000-0000-000000000048", "Finlandia Freight", 1, "9.10", True, True, "0.9500",
       "Tampere, FI", ["FI", "SE", "RU", "EE"], ["FI->SE"]),
    _p("00000000-0000-0000-0000-000000000049", "Sicily Strait Express", 2, "7.40", True, False, "1.1200",
       "Palermo, IT", ["IT", "MT", "TN"], ["IT->MT"]),
    _p("00000000-0000-0000-0000-000000000050", "Continental Connect", None, "8.70", True, True, "0.9100",
       "Frankfurt, DE", ["DE", "FR", "NL", "BE", "AT", "CH"], ["DE->FR", "DE->NL", "DE->AT"]),
    # North American carriers 51-58
    _p("00000000-0000-0000-0000-000000000051", "Great Lakes Freight", 1, "8.90", True, True, "1.0500",
       "Detroit, US", ["US", "CA"], ["US->CA", "US->US"]),
    _p("00000000-0000-0000-0000-000000000052", "Pacific Coast Haulers", 2, "9.20", True, False, "1.1800",
       "Los Angeles, US", ["US", "MX"], ["US->MX", "US->US"]),
    _p("00000000-0000-0000-0000-000000000053", "Maple Leaf Transport", 1, "8.60", True, True, "1.0200",
       "Toronto, CA", ["CA", "US"], ["CA->US", "CA->CA"]),
    _p("00000000-0000-0000-0000-000000000054", "Rio Grande Logistics", 3, "7.80", True, False, "0.8800",
       "Monterrey, MX", ["MX", "US"], ["MX->US", "MX->MX"]),
    _p("00000000-0000-0000-0000-000000000055", "Gulf Stream Express", 2, "8.40", True, True, "1.1200",
       "Houston, US", ["US", "MX"], ["US->MX"], pm=CarrierPricingModel.FLAT_RATE,
       flat="3200.00", fuel="8.50"),
    _p("00000000-0000-0000-0000-000000000056", "Aztec Cargo Lines", 3, "7.50", True, False, "0.8500",
       "Mexico City, MX", ["MX", "US", "GT"], ["MX->US", "MX->GT"]),
    _p("00000000-0000-0000-0000-000000000057", "Northern Star Carriers", 2, "8.80", True, True, "1.0800",
       "Winnipeg, CA", ["CA", "US"], ["CA->US"]),
    _p("00000000-0000-0000-0000-000000000058", "Lone Star Hauling", None, "7.10", True, False, "0.9500",
       "Dallas, US", ["US", "MX"], ["US->MX", "US->US"], pm=CarrierPricingModel.MARKET_ADJUSTED,
       fuel="6.20"),
)

CANONICAL_CARRIER_MAP: dict[UUID, CanonicalCarrier] = {
    c.id: c for c in CANONICAL_CARRIERS
}
