"""
End-to-end tests: IMD -> generated python classes -> read XTF -> write XTF -> ilivalidator.

The XTF is found in the model folder by the models listed in its header, see
`helpers.find_xtf`. The data in the repo is prevalidated, so the written XTF must pass
ilivalidator without errors. Known failures are marked xfail(strict=True) with the cause, so
a fix shows up as XPASS.
"""

from pathlib import Path

import pytest

from .helpers import (
    find_xtf,
    generate_library,
    imported_library,
    read_xtf,
    registered_types,
    run_ilivalidator,
    write_xtf,
    xtf_header,
)

MODEL_REPOSITORY = "http://models.interlis.ch"
MAX_REPORTED_ERRORS = 20

# known failures (triage 2026-10-19)
IMPORTED_TOPIC = (
    "generator: basket of a topic of an imported model (DMAV_Bodenbedeckung_V1_1) is read "
    "in the INTERLIS namespace, its classes are unknown"
)
ROLE_REF = "generator: association role embedded in the class (<role REF=…/>) is missing"
HEADER_ALIAS = "generator: INTERLIS 2.3 HEADERSECTION/ALIAS is missing in xtf_opening"
TRANSLATION = "generator: baskets of a translated model (TRANSLATION OF) are not known"
OID_ATTRIBUTE = "generator/codec: OID typed attribute (<BasketID OID=…/>) is lost on write"
INVALID_SOURCE = (
    "test data: source XTF fails ilivalidator 1.15.0 (198 x polygons overlay), geodienste "
    "validated it with 1.11.13"
)


def known_failure(imd_path: str, *reasons: str):
    return pytest.param(
        imd_path, marks=pytest.mark.xfail(reason="; ".join(reasons), strict=True)
    )


@pytest.mark.e2e
@pytest.mark.network_bound
@pytest.mark.parametrize(
    "imd_path",
    [
        known_failure("models/DMAVTYM_Alles_V1_1/DMAVTYM_Alles_V1_1.imd", IMPORTED_TOPIC),
        known_failure(
            "models/Elektrische_Anlagen_Nennspannung_36kV_V1_0/ElektrischeAnlagenNennspannungUeber36kV_V1.imd",
            TRANSLATION,
        ),
        "models/Fruchtfolgeflaechen_V1/Fruchtfolgeflaechen_V1.imd",
        "models/Gewaesserraum_V1_1/Gewaesserraum_V1_1.imd",
        "models/Grundwasservorkommen_V2_0/Grundwasservorkommen_V2_0.imd",
        "models/Hazard_Mapping_V1_3/Hazard_Mapping_V1_3.imd",
        "models/Holznutzungsbewilligung_V1/Holznutzungsbewilligung_V1_0.imd",
        known_failure(
            "models/Inventar_Wasserentnahmen_V1_1/InventarWasserentnahmen_V1_1.imd", ROLE_REF
        ),
        "models/Kantonale_Ausnahmetransportrouten_V1_0/ExceptionalLoadsRoute_V1.imd",
        "models/Kataster_belasteter_Standorte_V1_5/KbS_V1_5.imd",
        "models/LWB_Bewirtschaftungseinheiten_V2_0/LWB_Bewirtschaftungseinheiten_V2_0.imd",
        "models/LWB_Biodiversitaetsfoerderflaechen_Qualitaet_II_und_Vernetzung_V2_0/LWB_Biodiversitaetsfoerderflaechen_Qualitaet_II_und_Vernetzung_V2_0.imd",
        "models/LWB_Nutzungsflaechen_V2_0/LWB_Nutzungsflaechen_V2_0.imd",
        "models/LWB_Perimeter_LandwirtschaftlicheNutzflaeche_Soemmerung_V2_0/LWB_Perimeter_LandwirtschaftlicheNutzflaeche_Soemmerung_V2_0.imd",
        "models/LWB_Perimeter_Terrassenreben_V2_0/LWB_Perimeter_Terrassenreben_V2_0.imd",
        known_failure(
            "models/Laermempfindlichkeitsstufen_V1_2/Laermempfindlichkeitsstufen_V1_2.imd",
            INVALID_SOURCE,
            OID_ATTRIBUTE,
        ),
        known_failure("models/Leitungskataster/SIA405_LKMap_2015_2_d-20180427.imd", HEADER_ALIAS),
        known_failure(
            "models/Naturereigniskataster_V1_0/Naturereigniskataster_MGDM_V1.imd", ROLE_REF
        ),
        known_failure("models/Nutzungsplanung_V1_2/Nutzungsplanung_V1_2.imd", OID_ATTRIBUTE),
        "models/OeREBKRMtrsfr_V2_0/OeREBKRMtrsfr_V2_0.imd",
        known_failure(
            "models/Planerischer_Gewaesserschutz_V1_2/PlanerischerGewaesserschutz_V1_2.imd",
            HEADER_ALIAS,
        ),
        known_failure("models/Planungszonen_v1_1/Planungszonen_V1_1.imd", OID_ATTRIBUTE),
        "models/Rebbaukataster_V2/LWB_Rebbaukataster_V2_0.imd",
        known_failure(
            "models/Revitalisierung_Seeufer_V1_2/Revitalisierung_Seen_V1_2.imd", ROLE_REF
        ),
        known_failure(
            "models/Revitalisierungen_Fliessgewaesser_V1_2/Revitalisierung_Fliessgewaesser_V1_2.imd",
            ROLE_REF,
        ),
        "models/Richtplan_erneuerbare_Energien_V1_0/PlanDirecteurEnergiesRenouvelables_V1.imd",
        known_failure(
            "models/Richtplan_erneuerbare_Energien_V1_0/RichtplanungErneuerbareEnergien_V1.imd",
            TRANSLATION,
        ),
        "models/Rodungen_Rodungsersatz_V1_1/Rodungen_V1_1.imd",
        "models/SO_AFU_ABBAUSTELLEN_Publikation_20221103/SO_AFU_ABBAUSTELLEN_Publikation_20221103.imd",
        "models/SZ_Lebensraum_Fisch_V2/SZ_Lebensraum_Fisch_V2.imd",
        known_failure("models/SZ_Waldfeststellungen_V2/SZ_Waldfeststellungen_V2.imd", ROLE_REF),
        known_failure("models/SZ_Waldreservate_V3/SZ_Waldreservate_V3.imd", ROLE_REF),
        known_failure("models/Sanierung_Wasserkraft_V1_2/SanierungWasserkraft_V1_2.imd", ROLE_REF),
        known_failure("models/Statische_Waldgrenzen_v1_2/Waldgrenzen_V1_2.imd", OID_ATTRIBUTE),
        "models/Stromversorgung_Netzgebiete_V1_2/stromversorgungssicherheit_netzgebiete_LV95_V1_2.imd",
        known_failure("models/Waldabstandslinien_V1_2/Waldabstandslinien_V1_2.imd", OID_ATTRIBUTE),
        "models/Waldreservate_V1_1/Waldreservate_V1_1.imd",
        "models/Waldreservate_V2_0/Waldreservate_V2_0.imd",
        "models/Wildruhezonen_V2_1_1/Wildruhezonen_V2_1.imd",
    ],
)
def test_roundtrip_xtf(resource_path_root, tmp_path, ilivalidator_jar, imd_path):
    imd = Path(resource_path_root) / imd_path
    model_folder = imd.parent

    library = generate_library(imd, tmp_path / "generated")
    source_xtf = find_xtf(library, model_folder, tmp_path / "data")
    header = xtf_header(source_xtf)

    result_xtf = tmp_path / f"roundtrip_{source_xtf.name}"
    with imported_library(library) as xtf_opening, registered_types(library):
        transfer = read_xtf(source_xtf, xtf_opening.Transfer)
        assert isinstance(transfer, xtf_opening.Transfer)
        assert transfer.datasection.baskets, f"no baskets read from {source_xtf.name}"
        write_xtf(transfer, result_xtf, header.namespaces)

    log = tmp_path / "ilivalidator.log"
    result = run_ilivalidator(
        ilivalidator_jar, [result_xtf], [str(model_folder), MODEL_REPOSITORY], log
    )
    if result.returncode != 0:
        log_text = log.read_text(encoding="utf-8") if log.exists() else result.stderr
        errors = [line for line in log_text.splitlines() if line.startswith("Error")]
        pytest.fail(
            f"ilivalidator failed for {source_xtf.name} ({len(errors)} errors, "
            f"log: {log}):\n" + "\n".join(errors[:MAX_REPORTED_ERRORS] or [log_text[-2000:]])
        )
