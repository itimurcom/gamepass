from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class SiglListDef:
    key: str
    sigl_id: str
    title: str
    group: str


def get_default_sigl_lists() -> List[SiglListDef]:
    return [
        SiglListDef("pcgaVTaz", "609d944c-d395-4c0a-9ea4-e9f39b52c1ad", "All PC Game Pass games (A-Z)", "Core"),
        SiglListDef("pcgaVTpopular", "a884932a-f02b-40c8-a903-a008c23b1df1", "Popular on PC", "Core"),
        SiglListDef("XGPPMPRecentlyAdded", "3fdd7f57-7092-4b65-bd40-5a9dac1b2b84", "Recently added", "Core"),
        SiglListDef("pccomingsoon", "4165f752-d702-49c8-886b-fb57936f6bae", "Coming soon", "Core"),
        SiglListDef("SubsXGPLeavingSoon", "cc7fc951-d00f-410e-9e02-5e4628e04163", "Leaving soon", "Core"),
        SiglListDef("pdoPC", "4b59700c-801f-494a-a34c-842b8c98f154", "Play Day One", "Core"),
        SiglListDef("eaplayPC", "1d33fbb9-b895-4732-a8ca-a55c8b99fa2c", "EA Play (PC)", "Publishers"),
        SiglListDef("bethpc", "79fe89cf-f6a3-48d4-af6c-de4482cf4a51", "Bethesda", "Publishers"),
        SiglListDef("riotgamespc", "7008e21d-2b70-4fab-b6dc-a220ebae001f", "Riot Games", "Publishers"),
        SiglListDef("ftpbenefitspc", "3a6b073e-9719-4071-b7a3-6d836f5d949e", "Free-to-play benefits (PC)", "Publishers"),
        SiglListDef("pcgaVTIndies", "1e2ce757-e84f-4d2c-9243-34b81912644a", "Indies", "Genres"),
        SiglListDef("pcgaVTRPG", "c621daed-3d22-4745-afc9-19ed77a2e9be", "RPG", "Genres"),
        SiglListDef("pcgaVTStrategy", "7a3b01ac-93e4-4d52-81ad-980bc4cb4ff5", "Strategy", "Genres"),
        SiglListDef("pcgaVTFamily", "0f0bccc0-cdc8-4e1a-bfca-4b7da5c6c418", "Family", "Genres"),
        SiglListDef("pcgaVTSimulation", "f0e9ffe0-176e-41af-be11-c40a05d26e2c", "Simulation", "Genres"),
        SiglListDef("XGPPMPActionAdventure", "0f4967a6-7226-48bd-8ab4-a6ef40b09981", "Action & Adventure", "Genres"),
        SiglListDef("XGPPMPShooters", "590d891f-0f12-4bd6-8d58-28c5d612ba38", "Shooters", "Genres"),
        SiglListDef("sportsPC", "6661f37d-6159-4c9c-81d8-668af0a78b04", "Sports", "Genres"),
        SiglListDef("XGPPMPFamilyFriendly", "8e5089f1-5947-4ce1-9db1-94644556e493", "Family friendly", "Genres"),
    ]


def build_lists_index(lists: List[SiglListDef]) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    for x in lists:
        out[x.key] = {"sigl_id": x.sigl_id, "title": x.title, "group": x.group}
    return out
