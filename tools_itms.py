# tools_itms.py
"""ITMS21+ tool implementations for the MCP server."""

import json
from typing import Optional

from itms_client import (
    get,
    get_list,
    strip_html,
    format_date,
    format_amount,
    safe_get,
)


# ──────────────────────────────────────────────
# Tool 1: search_open_calls
# ──────────────────────────────────────────────
async def search_open_calls(
    code: str = "",
    programme_code: str = "",
    applicant_type_kod: str = "",
    specific_objective_id: int = 0,
    region_nuts_kod: str = "",
    limit: int = 20,
) -> str:
    """
    Search open (not yet closed) calls for EU funding applications (výzvy) in Slovakia.

    There is NO free-text search on call names. To find calls by topic, use `code`
    (substring on call code) or leave filters empty to list all open calls.

    Args:
        code: Substring match on call CODE (e.g. "PSK-UV" matches
            "PSK-UV-005-2024-DV-ESF+", "MRK" finds codes containing MRK,
            "005" finds calls with 005 in the code).
        programme_code: Filter by programme CODE (e.g. "401000" for Programme
            Slovakia). NOT a name search — use the numeric programme code.
        applicant_type_kod: Filter by eligible applicant kodZdroj code
            (e.g. "1009801" for municipalities/obce). NOT a name search.
            Common codes: 1009801=Obec/mesto, 1009321=Rozpočtová organizácia,
            1009331=Príspevková organizácia.
        specific_objective_id: Filter by specific objective ID (integer).
        region_nuts_kod: Filter by NUTS region full kod (e.g. "1006SK041"
            for Prešovský kraj, "1006SK042" for Košický kraj).
            NOT a name search — use the full NUTS code with 1006 prefix.
        limit: Maximum number of results (default 20).

    Returns:
        List of open calls with name, code, deadline, funding amount,
        eligible applicants, and specific objective.
    """
    params = {
        "ajUkoncene": "false",
    }
    if code:
        params["kod"] = code
    if programme_code:
        params["program"] = programme_code
    if applicant_type_kod:
        params["opravnenyZiadatel"] = applicant_type_kod
    if specific_objective_id:
        params["specifickyCielProgramuId"] = str(specific_objective_id)
    if region_nuts_kod:
        params["miestoRealizacie"] = region_nuts_kod

    items = await get_list("/vyzva", limit=limit, extra_params=params)

    if not items:
        return "No open calls found matching your criteria."

    lines = []
    for c in items:
        lines.append(f"**{c.get('nazovSk', 'N/A')}**")
        lines.append(f"  Code: {c.get('kod', 'N/A')}")
        lines.append(f"  ID: {c.get('id', 'N/A')}")
        lines.append(f"  EU Funding: {format_amount(c.get('sumaEu'))}")
        lines.append(f"  SR Co-financing: {format_amount(c.get('sumaSr'))}")
        lines.append(f"  Announced: {format_date(c.get('datumVyhlasenia'))}")
        lines.append(f"  Type: {c.get('typ', 'N/A')}")
        lines.append(f"  Programme: {safe_get(c, 'program', 'nazovSk')}")

        # Specific objectives
        sc_list = c.get("specifickyCielProgramu", [])
        if sc_list:
            sc_names = [sc.get("nazovSk", "") for sc in sc_list if sc.get("nazovSk")]
            lines.append(f"  Specific Objectives: {'; '.join(sc_names)}")

        # Eligible applicants
        ziadatel_list = c.get("ziadatel", [])
        if ziadatel_list:
            applicants = [z.get("nazov", "") for z in ziadatel_list if z.get("nazov")]
            if applicants:
                lines.append(f"  Eligible Applicants: {'; '.join(applicants[:5])}")

        # Regions
        mr_list = c.get("miestoRealizacie", [])
        if mr_list:
            regions = [m.get("nazovSk", "") for m in mr_list if m.get("nazovSk")]
            if regions:
                lines.append(f"  Regions: {', '.join(regions[:5])}")

        lines.append("")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Tool 2: get_call_detail
# ──────────────────────────────────────────────
async def get_call_detail(call_id: int) -> str:
    """
    Get complete detail of a specific EU funding call (výzva) by its ID.

    Returns full information: eligibility conditions, funding amounts,
    required indicators, application attachments, contact persons,
    and all conditions for receiving support (podmienky poskytnutia pomoci).

    Use this after search_open_calls to get full requirements for a specific call.

    Args:
        call_id: The ID of the call to retrieve.

    Returns:
        Full call detail with all fields.
    """
    data = await get(f"/vyzva/id/{call_id}")

    lines = []
    lines.append(f"# {data.get('nazovSk', 'N/A')}")
    lines.append(f"**Code:** {data.get('kod', 'N/A')}")
    lines.append(f"**ID:** {data.get('id', 'N/A')}")
    lines.append(f"**Announced:** {format_date(data.get('datumVyhlasenia'))}")
    lines.append(f"**Open:** {'Yes' if data.get('vyhlasena') else 'No'}")
    lines.append(f"**Closed:** {'Yes' if data.get('uzavreta') else 'No'}")
    lines.append(f"**Cancelled:** {'Yes' if data.get('zrusena') else 'No'}")
    lines.append(f"**Type:** {data.get('typ', 'N/A')}")
    lines.append(f"**Kind:** {data.get('druh', 'N/A')}")
    lines.append("")

    # Funding
    lines.append("## Funding")
    lines.append(f"  EU Amount: {format_amount(data.get('sumaEu'))}")
    lines.append(f"  SR Co-financing: {format_amount(data.get('sumaSr'))}")
    lines.append("")

    # Programme
    lines.append("## Programme")
    lines.append(f"  {safe_get(data, 'program', 'nazovSk')}")
    lines.append(f"  Code: {safe_get(data, 'program', 'kod')}")
    lines.append("")

    # Specific objectives
    sc_list = data.get("specifickyCielProgramu", [])
    if sc_list:
        lines.append("## Specific Objectives")
        for sc in sc_list:
            lines.append(f"  - {sc.get('nazovSk', 'N/A')} ({sc.get('kod', '')})")
            priorita = sc.get("priorita", {})
            if priorita:
                lines.append(f"    Priority: {priorita.get('nazovSk', 'N/A')}")
        lines.append("")

    # Eligible applicants
    ziadatel_list = data.get("ziadatel", [])
    if ziadatel_list:
        lines.append("## Eligible Applicants")
        for z in ziadatel_list:
            lines.append(f"  - {z.get('nazov', 'N/A')}")
        lines.append("")

    # Regions
    mr_list = data.get("miestoRealizacie", [])
    if mr_list:
        lines.append("## Eligible Regions")
        for m in mr_list:
            lines.append(f"  - {m.get('nazovSk', 'N/A')} ({m.get('kodZdroj', '')})")
        lines.append("")

    # Call objective / aim
    ciel = strip_html(data.get("cielVyzvy"))
    if ciel:
        lines.append("## Call Objective (Cieľ výzvy)")
        lines.append(ciel)
        lines.append("")

    # Conditions for support
    podmienky = data.get("podmienkaPoskytnutiaPrispevku", [])
    if podmienky:
        lines.append("## Conditions for Support (Podmienky poskytnutia príspevku)")
        for p in podmienky:
            lines.append(f"  - {strip_html(p.get('nazov', ''))}: {strip_html(p.get('popis', ''))}")
        lines.append("")

    # Indicators
    for label, key in [("Output Indicators", "ukazovatelVystupovy"), ("Result Indicators", "ukazovatelVysledkovy")]:
        indicators = data.get(key, [])
        if indicators:
            lines.append(f"## {label}")
            for ind in indicators:
                lines.append(f"  - {ind.get('nazovSk', ind.get('nazov', 'N/A'))} ({ind.get('kod', '')})")
                mj = ind.get("mernaJednotka", {})
                if mj:
                    lines.append(f"    Unit: {mj.get('nazovSk', 'N/A')}")
            lines.append("")

    # Contact
    kontakt = data.get("kontaktnaOsoba", [])
    if kontakt:
        lines.append("## Contact")
        for k in kontakt:
            lines.append(f"  - {k.get('meno', '')} {k.get('priezvisko', '')} — {k.get('email', 'N/A')}")
        lines.append("")

    # Documents
    dokumenty = data.get("dokument", [])
    if dokumenty:
        lines.append("## Documents")
        for doc in dokumenty[:20]:
            lines.append(f"  - {doc.get('nazov', 'N/A')}")
        lines.append("")

    # Statistics
    lines.append("## Application Statistics")
    lines.append(f"  Submitted: {data.get('pocetPredlozenychZiadosti', 'N/A')}")
    lines.append(f"  Approved: {data.get('pocetSchvalenychZiadosti', 'N/A')}")
    lines.append(f"  Rejected: {data.get('pocetNeschvalenychZiadosti', 'N/A')}")
    lines.append(f"  In process: {data.get('pocetZiadostiVKonani', 'N/A')}")
    lines.append(f"  Realised projects: {data.get('pocetRealizovanychProjektov', 'N/A')}")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Tool 3: search_planned_calls
# ──────────────────────────────────────────────
async def search_planned_calls(
    code: str = "",
    programme_code: str = "",
    applicant_type_kod: str = "",
    region_nuts_kod: str = "",
    limit: int = 20,
) -> str:
    """
    Search planned (upcoming) EU funding calls that are not yet open.

    Use this to help applicants prepare in advance.

    Args:
        code: Substring match on the planned call CODE.
        programme_code: Filter by programme CODE (e.g. "401000").
        applicant_type_kod: Filter by applicant kodZdroj code (e.g. "1009801").
        region_nuts_kod: Filter by NUTS region full kod (e.g. "1006SK041").
        limit: Maximum number of results (default 20).

    Returns:
        List of planned calls with details.
    """
    params = {"ajZrusene": "false"}
    if code:
        params["kod"] = code
    if programme_code:
        params["program"] = programme_code
    if applicant_type_kod:
        params["opravnenyZiadatel"] = applicant_type_kod
    if region_nuts_kod:
        params["miestoRealizacie"] = region_nuts_kod

    items = await get_list("/planovanavyzva", limit=limit, extra_params=params)

    if not items:
        return "No planned calls found matching your criteria."

    lines = []
    for c in items:
        lines.append(f"**{c.get('nazovSk', 'N/A')}**")
        lines.append(f"  Code: {c.get('kod', 'N/A')}")
        lines.append(f"  ID: {c.get('id', 'N/A')}")
        lines.append(f"  EU Funding: {format_amount(c.get('sumaEu'))}")
        lines.append(f"  Planned Announcement (1st round): {format_date(c.get('datumVyhlasenia1Kolo'))}")
        lines.append(f"  Programme: {safe_get(c, 'program', 'nazovSk')}")
        lines.append(f"  Cancelled: {'Yes' if c.get('zrusena') else 'No'}")

        # Specific objectives
        sc_list = c.get("specifickyCielProgramu", [])
        if sc_list:
            sc_names = [sc.get("nazovSk", "") for sc in sc_list if sc.get("nazovSk")]
            lines.append(f"  Specific Objectives: {'; '.join(sc_names)}")

        # Eligible applicants
        ziadatel_list = c.get("ziadatel", [])
        if ziadatel_list:
            applicants = [z.get("nazov", "") for z in ziadatel_list if z.get("nazov")]
            if applicants:
                lines.append(f"  Eligible Applicants: {'; '.join(applicants[:5])}")

        # Regions
        mr_list = c.get("miestoRealizacie", [])
        if mr_list:
            regions = [m.get("nazovSk", "") for m in mr_list if m.get("nazovSk")]
            if regions:
                lines.append(f"  Regions: {', '.join(regions[:5])}")

        lines.append("")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Tool 4: search_approved_applications
# ──────────────────────────────────────────────
async def search_approved_applications(
    code: str = "",
    applicant_name: str = "",
    call_id: int = 0,
    programme_code: str = "",
    region_name: str = "",
    limit: int = 10,
) -> str:
    """
    Search approved grant applications (schválené žiadosti o NFP).

    Use this to find real examples of successful applications.

    IMPORTANT: The BEST and MOST RELIABLE way to find applications for a specific
    call is by call_id (integer). Get the call ID from search_open_calls.

    Args:
        code: Substring match on APPLICATION CODE (e.g. "NFP401406").
        applicant_name: Substring match on applicant entity NAME
            (e.g. "Varhaňovce" finds Obec Varhaňovce, "obec" finds
            all applications by entities with "obec" in the name).
        call_id: Filter by call ID (integer, exact match). ALWAYS use this
            to find applications under a specific call — it is the only
            reliable call filter. Get the ID from search_open_calls.
        programme_code: Filter by programme CODE (e.g. "401000").
        region_name: Substring match on region NAME in Slovak
            (e.g. "Prešovský" for Prešov region).
        limit: Maximum number of results (default 10).

    Returns:
        List of approved applications with code, name, applicant, call,
        approved amount, dates, and status.
    """
    params = {"schvalena": "true"}
    if code:
        params["kod"] = code
    if applicant_name:
        params["ziadatel"] = applicant_name
    if call_id:
        params["vyzvaId"] = str(call_id)
    if programme_code:
        params["program"] = programme_code
    if region_name:
        params["miestoRealizacie"] = region_name

    items = await get_list("/zonfp", limit=limit, extra_params=params)

    if not items:
        return "No approved applications found matching your criteria."

    lines = []
    for a in items:
        lines.append(f"**{a.get('nazov', 'N/A')}**")
        lines.append(f"  Code: {a.get('kod', 'N/A')}")
        lines.append(f"  ID: {a.get('id', 'N/A')}")
        lines.append(f"  Applicant: {safe_get(a, 'ziadatel', 'nazov')}")
        lines.append(f"  Call: {safe_get(a, 'vyzva', 'nazovSk')} ({safe_get(a, 'vyzva', 'kod')})")
        lines.append(f"  Requested Total: {format_amount(a.get('sumaZiadanaCelkova'))}")
        lines.append(f"  Requested NFP: {format_amount(a.get('sumaZiadanaNFP'))}")
        lines.append(f"  Approved Total: {format_amount(a.get('sumaSchvalenaCelkova'))}")
        lines.append(f"  Approved NFP: {format_amount(a.get('sumaSchvalenaNFP'))}")
        lines.append(f"  Status: {a.get('stav', 'N/A')}")
        lines.append(f"  Submitted: {format_date(a.get('datumPredlozenia'))}")
        lines.append(f"  Approved: {format_date(a.get('datumSchvalenia'))}")
        lines.append(f"  Programme: {safe_get(a, 'vyzva', 'program', 'nazovSk')}")

        lines.append("")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Tool 5: get_application_detail
# ──────────────────────────────────────────────
async def get_application_detail(application_id: int) -> str:
    """
    Get complete detail of a specific grant application (žiadosť o NFP) by ID.

    Returns the full application content including:
    - popis: project description
    - ucel: project purpose/objective
    - popisVychodiskovejSituacie: baseline situation description
    - popisSposobuRealizacie: implementation method description
    - popisSituaciePoRealizacii: post-realisation situation
    - popisKapacityZiadatela: applicant capacity description
    - Budget structure, activities, indicators, and co-financing rates

    Use this to examine real approved applications as reference examples for
    drafting new applications.

    Args:
        application_id: The ID of the application to retrieve.

    Returns:
        Full application detail with all significant text fields.
    """
    data = await get(f"/zonfp/id/{application_id}")

    lines = []
    lines.append(f"# {data.get('nazov', 'N/A')}")
    lines.append(f"**Code:** {data.get('kod', 'N/A')}")
    lines.append(f"**ID:** {data.get('id', 'N/A')}")
    lines.append(f"**Acronym:** {data.get('akronym', 'N/A')}")
    lines.append(f"**Status:** {data.get('stav', 'N/A')}")
    lines.append(f"**Approved:** {'Yes' if data.get('schvalena') else 'No'}")
    lines.append("")

    # Applicant
    ziadatel = data.get("ziadatel", {})
    if ziadatel:
        lines.append("## Applicant (Žiadateľ)")
        lines.append(f"  Name: {ziadatel.get('nazov', 'N/A')}")
        lines.append(f"  IČO: {ziadatel.get('ico', 'N/A')}")
        adresa = ziadatel.get("adresa", {})
        if adresa:
            lines.append(f"  Address: {adresa.get('ulica', '')} {adresa.get('cislo', '')}, {adresa.get('psc', '')} {adresa.get('obec', '')}")
        lines.append("")

    # Call info
    vyzva = data.get("vyzva", {})
    if vyzva:
        lines.append("## Call (Výzva)")
        lines.append(f"  Name: {vyzva.get('nazovSk', 'N/A')}")
        lines.append(f"  Code: {vyzva.get('kod', 'N/A')}")
        lines.append(f"  Programme: {safe_get(vyzva, 'program', 'nazovSk')}")
        lines.append("")

    # Funding
    lines.append("## Funding")
    lines.append(f"  Requested Total: {format_amount(data.get('sumaZiadanaCelkova'))}")
    lines.append(f"  Requested NFP: {format_amount(data.get('sumaZiadanaNFP'))}")
    lines.append(f"  Requested Own Resources: {format_amount(data.get('sumaZiadanaVZ'))}")
    lines.append(f"  Approved Total: {format_amount(data.get('sumaSchvalenaCelkova'))}")
    lines.append(f"  Approved NFP: {format_amount(data.get('sumaSchvalenaNFP'))}")
    lines.append(f"  Approved Own Resources: {format_amount(data.get('sumaSchvalenaVZ'))}")
    lines.append("")

    # Dates
    lines.append("## Dates")
    lines.append(f"  Submitted: {format_date(data.get('datumPredlozenia'))}")
    lines.append(f"  Registered: {format_date(data.get('datumRegistracie'))}")
    lines.append(f"  Approved: {format_date(data.get('datumSchvalenia'))}")
    lines.append(f"  Requested Start: {format_date(data.get('datumZiadanyZaciatkuHlavnychAktivit'))}")
    lines.append(f"  Requested End: {format_date(data.get('datumZiadanyKoncaHlavnychAktivit'))}")
    lines.append(f"  Approved Start: {format_date(data.get('datumSchvalenyZaciatkuHlavnychAktivit'))}")
    lines.append(f"  Approved End: {format_date(data.get('datumSchvalenyKoncaHlavnychAktivit'))}")
    lines.append(f"  Requested Duration (months): {data.get('dlzkaZiadanaCelkovaHlavnychAktivit', 'N/A')}")
    lines.append(f"  Approved Duration (months): {data.get('dlzkaSchvalenaCelkovaHlavnychAktivit', 'N/A')}")
    lines.append("")

    # === KEY TEXT FIELDS ===
    text_fields = [
        ("Project Description (Popis projektu)", "popis"),
        ("Project Purpose (Účel projektu)", "ucel"),
        ("Target Group (Cieľová skupina)", "cielovaSkupina"),
    ]
    for label, key in text_fields:
        val = strip_html(data.get(key))
        if val:
            lines.append(f"## {label}")
            lines.append(val)
            lines.append("")

    # Specific objectives
    sc_list = data.get("specifickyCielProgramu", [])
    if sc_list:
        lines.append("## Specific Objectives")
        for sc in sc_list:
            lines.append(f"  - {sc.get('nazovSk', 'N/A')} ({sc.get('kod', '')})")
        lines.append("")

    # Regions
    mr_list = data.get("miestoRealizacie", [])
    if mr_list:
        lines.append("## Implementation Regions")
        for m in mr_list:
            lines.append(f"  - {m.get('nazovSk', 'N/A')}")
        lines.append("")

    # Activities
    for label, key in [("Requested Activities", "aktivity"), ("Approved Activities", "aktivitySchvalene")]:
        aktivity = data.get(key, [])
        if aktivity:
            lines.append(f"## {label}")
            for akt in aktivity:
                lines.append(f"  - {akt.get('nazov', 'N/A')}")
                popis_akt = strip_html(akt.get("popis"))
                if popis_akt:
                    lines.append(f"    Description: {popis_akt[:500]}")
            lines.append("")

    # Indicators
    for label, key in [
        ("Requested Output Indicators", "ukazovatelZiadanyVystupu"),
        ("Approved Output Indicators", "ukazovatelSchvalenyVystupu"),
        ("Requested Result Indicators", "ukazovatelZiadanyVysledku"),
        ("Approved Result Indicators", "ukazovatelSchvalenyVysledku"),
    ]:
        indicators = data.get(key, [])
        if indicators:
            lines.append(f"## {label}")
            for ind in indicators:
                lines.append(f"  - {ind.get('nazovSk', ind.get('nazov', 'N/A'))} ({ind.get('kod', '')})")
                lines.append(f"    Target: {ind.get('cielovaHodnota', 'N/A')}")
                mj = ind.get("mernaJednotka", {})
                if mj:
                    lines.append(f"    Unit: {mj.get('nazovSk', 'N/A')}")
            lines.append("")

    # Budget items
    for label, key in [("Requested Budget", "polozkyRozpoctu"), ("Approved Budget", "polozkyRozpoctuSchvalene")]:
        budget = data.get(key, [])
        if budget:
            lines.append(f"## {label}")
            for b in budget:
                lines.append(f"  - {b.get('nazov', 'N/A')}: {format_amount(b.get('suma'))}")
            lines.append("")

    # Partners
    partners = data.get("partner", [])
    if partners:
        lines.append("## Partners")
        for p in partners:
            lines.append(f"  - {p.get('nazov', safe_get(p, 'subjekt', 'nazov'))}")
        lines.append("")

    # Evaluation score
    score = data.get("pocetBodovHodnoteniaCelkovy")
    if score is not None:
        lines.append(f"## Evaluation Score: {score}")
        lines.append("")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Tool 6: search_projects
# ──────────────────────────────────────────────
async def search_projects(
    code: str = "",
    beneficiary_name: str = "",
    call_id: int = 0,
    programme_code: str = "",
    region_name: str = "",
    in_realisation: bool = True,
    completed: bool = False,
    limit: int = 10,
) -> str:
    """
    Search EU-funded projects in Slovakia (projekty).

    Returns projects with their contracted amounts, realisation dates,
    beneficiary, and implementation status.

    IMPORTANT: Use call_id (integer) to find projects under a specific call.

    Args:
        code: Substring match on PROJECT CODE (e.g. "NFP401406").
        beneficiary_name: Substring match on beneficiary entity NAME
            (e.g. "obec" finds projects by municipalities, "Bratislava"
            finds projects by entities with Bratislava in the name).
        call_id: Filter by call ID (integer, exact match). ALWAYS use this
            to find projects under a specific call.
        programme_code: Filter by programme CODE (e.g. "401000").
        region_name: Substring match on region NAME or NUTS kod
            (e.g. "Prešovský" or "1006SK041" — both work for Prešov region).
        in_realisation: If True, only show projects in realisation (default True).
        completed: If True, only show completed projects (default False).
        limit: Maximum number of results (default 10).

    Returns:
        List of projects with key details.
    """
    params = {}
    if in_realisation:
        params["vrealizacii"] = "true"
    if completed:
        params["ukonceny"] = "true"
    if code:
        params["kod"] = code
    if beneficiary_name:
        params["prijimatel"] = beneficiary_name
    if call_id:
        params["vyzvaId"] = str(call_id)
    if programme_code:
        params["program"] = programme_code
    if region_name:
        params["miestorealizacie"] = region_name

    items = await get_list("/projekt", limit=limit, extra_params=params)

    if not items:
        return "No projects found matching your criteria."

    lines = []
    for p in items:
        lines.append(f"**{p.get('nazov', 'N/A')}**")
        lines.append(f"  Code: {p.get('kod', 'N/A')}")
        lines.append(f"  ID: {p.get('id', 'N/A')}")
        lines.append(f"  Beneficiary: {safe_get(p, 'prijimatel', 'nazov')}")
        lines.append(f"  Contracted Amount: {format_amount(p.get('celkovaZazmluvnenaSuma'))}")
        lines.append(f"  NFP Amount: {format_amount(p.get('zazmluvnenaSumaNfp'))}")
        lines.append(f"  Status: {p.get('stav', 'N/A')}")
        lines.append(f"  In Realisation: {'Yes' if p.get('vrealizacii') else 'No'}")
        lines.append(f"  Call: {safe_get(p, 'vyzva', 'nazovSk')} ({safe_get(p, 'vyzva', 'kod')})")
        lines.append(f"  Programme: {safe_get(p, 'vyzva', 'program', 'nazovSk')}")

        # Regions
        mr_list = p.get("miestoRealizacie", [])
        if mr_list:
            regions = [m.get("nazovSk", "") for m in mr_list if m.get("nazovSk")]
            if regions:
                lines.append(f"  Regions: {', '.join(regions[:5])}")

        lines.append("")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Tool 7: get_project_detail
# ──────────────────────────────────────────────
async def get_project_detail(project_id: int) -> str:
    """
    Get complete detail of a funded EU project by ID.

    Returns full project information: contracted amount, budget breakdown,
    activities, measurable output and result indicators with target values,
    realisation dates, beneficiary details, and contract information.

    Use this to understand exactly what a successfully funded project
    committed to in terms of activities and measurable results.

    Args:
        project_id: The ID of the project to retrieve.

    Returns:
        Full project detail with all significant fields.
    """
    data = await get(f"/projekt/id/{project_id}")

    lines = []
    lines.append(f"# {data.get('nazov', 'N/A')}")
    lines.append(f"**Code:** {data.get('kod', 'N/A')}")
    lines.append(f"**ID:** {data.get('id', 'N/A')}")
    lines.append(f"**Acronym:** {data.get('akronym', 'N/A')}")
    lines.append(f"**Status:** {data.get('stav', 'N/A')}")
    lines.append(f"**In Realisation:** {'Yes' if data.get('vrealizacii') else 'No'}")
    lines.append(f"**Completed:** {'Yes' if data.get('ukonceny') else 'No'}")
    lines.append("")

    # Beneficiary
    prijimatel = data.get("prijimatel", {})
    if prijimatel:
        lines.append("## Beneficiary (Prijímateľ)")
        lines.append(f"  Name: {prijimatel.get('nazov', 'N/A')}")
        lines.append(f"  IČO: {prijimatel.get('ico', 'N/A')}")
        adresa = prijimatel.get("adresa", {})
        if adresa:
            lines.append(f"  Address: {adresa.get('ulica', '')} {adresa.get('cislo', '')}, {adresa.get('psc', '')} {adresa.get('obec', '')}")
        lines.append("")

    # Call info
    vyzva = data.get("vyzva", {})
    if vyzva:
        lines.append("## Call (Výzva)")
        lines.append(f"  Name: {vyzva.get('nazovSk', 'N/A')}")
        lines.append(f"  Code: {vyzva.get('kod', 'N/A')}")
        lines.append(f"  Programme: {safe_get(vyzva, 'program', 'nazovSk')}")
        lines.append("")

    # Funding
    lines.append("## Funding")
    lines.append(f"  Total Contracted: {format_amount(data.get('celkovaZazmluvnenaSuma'))}")
    lines.append(f"  NFP Contracted: {format_amount(data.get('zazmluvnenaSumaNfp'))}")
    lines.append("")

    # Dates
    lines.append("## Dates")
    lines.append(f"  Planned Start: {format_date(data.get('planovanaRealizaciaZaciatok'))}")
    lines.append(f"  Planned End: {format_date(data.get('planovanaRealizaciaKoniec'))}")
    lines.append(f"  Actual Start: {format_date(data.get('skutocnaRealizaciaZaciatok'))}")
    lines.append(f"  Activities Start: {format_date(data.get('datumZaciatkuHlavnychAktivit'))}")
    lines.append(f"  Activities End: {format_date(data.get('datumKoncaHlavnychAktivit'))}")
    lines.append(f"  Duration (months): {data.get('dlzkaCelkovaHlavnychAktivit', 'N/A')}")
    lines.append("")

    # === KEY TEXT FIELDS ===
    text_fields = [
        ("Project Description (Popis projektu)", "popis"),
        ("Project Purpose (Účel projektu)", "ucel"),
        ("Baseline Situation (Popis východiskovej situácie)", "popisVychodiskovejSituacie"),
        ("Implementation Method (Popis spôsobu realizácie)", "popisSposobuRealizacie"),
        ("Post-Realisation Situation (Popis situácie po realizácii)", "popisSituaciePoRealizacii"),
        ("Applicant Capacity (Popis kapacity prijímateľa)", "popisKapacityPrijimatela"),
        ("Target Group (Cieľová skupina)", "cielovaSkupina"),
    ]
    for label, key in text_fields:
        val = strip_html(data.get(key))
        if val:
            lines.append(f"## {label}")
            lines.append(val)
            lines.append("")

    # Specific objectives
    sc_list = data.get("specifickyCielProgramu", [])
    if sc_list:
        lines.append("## Specific Objectives")
        for sc in sc_list:
            lines.append(f"  - {sc.get('nazovSk', 'N/A')} ({sc.get('kod', '')})")
        lines.append("")

    # Regions
    mr_list = data.get("miestoRealizacie", [])
    if mr_list:
        lines.append("## Implementation Regions")
        for m in mr_list:
            lines.append(f"  - {m.get('nazovSk', 'N/A')}")
        lines.append("")

    # Activities
    aktivity = data.get("aktivity", [])
    if aktivity:
        lines.append("## Activities")
        for akt in aktivity:
            lines.append(f"  - {akt.get('nazov', 'N/A')}")
            popis_akt = strip_html(akt.get("popis"))
            if popis_akt:
                lines.append(f"    {popis_akt[:500]}")
        lines.append("")

    # Indicators
    for label, key in [
        ("Output Indicators", "ukazovatelVystupu"),
        ("Result Indicators", "ukazovatelVysledku"),
    ]:
        indicators = data.get(key, [])
        if indicators:
            lines.append(f"## {label}")
            for ind in indicators:
                lines.append(f"  - {ind.get('nazovSk', ind.get('nazov', 'N/A'))} ({ind.get('kod', '')})")
                lines.append(f"    Target: {ind.get('cielovaHodnota', 'N/A')}")
                mj = ind.get("mernaJednotka", {})
                if mj:
                    lines.append(f"    Unit: {mj.get('nazovSk', 'N/A')}")
            lines.append("")

    # Budget items
    budget = data.get("polozkyRozpoctu", [])
    if budget:
        lines.append("## Budget Items")
        for b in budget:
            lines.append(f"  - {b.get('nazov', 'N/A')}: {format_amount(b.get('suma'))}")
        lines.append("")

    # Partners
    partners = data.get("partner", [])
    if partners:
        lines.append("## Partners")
        for p in partners:
            lines.append(f"  - {safe_get(p, 'subjekt', 'nazov') or p.get('nazov', 'N/A')}")
        lines.append("")

    # Contracts
    zmluvy = data.get("zmluvaProjekt")
    if zmluvy:
        lines.append("## Contract")
        if isinstance(zmluvy, dict):
            zmluvy = [zmluvy]
        elif not isinstance(zmluvy, list):
            zmluvy = []
        for z in zmluvy:
            if isinstance(z, dict):
                lines.append(f"  Contract No: {z.get('cislo', 'N/A')}")
                lines.append(f"  Valid from: {format_date(z.get('datumUcinnosti'))}")
                url = z.get("url")
                if url:
                    lines.append(f"  URL: {url}")
        lines.append("")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Tool 8: get_programme_structure
# ──────────────────────────────────────────────
async def get_programme_structure(programme_code: str = "") -> str:
    """
    Get the EU Programme structure for Slovakia (Program Slovensko 2021-2027).

    Returns the hierarchy: Programme -> Priorities -> Specific Objectives ->
    Types of Action. Use this to understand which specific objective a call
    falls under and what the broader policy context is.

    Leave programme_code empty to list all programmes.

    Args:
        programme_code: Optional programme code to filter (e.g. '401000' for Programme Slovakia).

    Returns:
        Programme structure with priorities and specific objectives.
    """
    # Get programmes
    programmes = await get_list("/program", limit=-1)

    if programme_code:
        programmes = [p for p in programmes if p.get("kod", "").startswith(programme_code) or p.get("skratka", "") == programme_code]

    if not programmes:
        return "No programmes found matching your criteria."

    # Get specific objectives
    spec_ciele = await get_list("/specifickycielprogramu", limit=-1)

    lines = []
    for prog in programmes:
        prog_id = prog.get("id")
        lines.append(f"# {prog.get('nazovSk', 'N/A')}")
        lines.append(f"  Code: {prog.get('kod', 'N/A')}")
        lines.append(f"  Abbreviation: {prog.get('skratka', 'N/A')}")
        lines.append(f"  EU Funding: {format_amount(prog.get('sumaEu'))}")
        lines.append(f"  SR Co-financing: {format_amount(prog.get('sumaSr'))}")
        lines.append(f"  Total: {format_amount(prog.get('sumaSpolu'))}")
        lines.append(f"  CCI Code: {prog.get('kodCCI', 'N/A')}")

        # Managing authority
        ro = prog.get("riadiaciOrgan", {})
        if ro:
            lines.append(f"  Managing Authority: {ro.get('nazov', safe_get(ro, 'subjekt', 'nazov'))}")
        lines.append("")

        # Group specific objectives by priority
        prog_sc = [sc for sc in spec_ciele if safe_get(sc, "program", "id") == prog_id]

        # Group by priority
        priorities = {}
        for sc in prog_sc:
            prio = sc.get("priorita", {})
            prio_key = prio.get("kod", "unknown") if prio else "unknown"
            if prio_key not in priorities:
                priorities[prio_key] = {
                    "nazov": prio.get("nazovSk", "N/A") if prio else "N/A",
                    "objectives": [],
                }
            priorities[prio_key]["objectives"].append(sc)

        if priorities:
            lines.append("## Priorities and Specific Objectives")
            for prio_kod, prio_data in sorted(priorities.items()):
                lines.append(f"  ### {prio_data['nazov']} ({prio_kod})")
                for sc in prio_data["objectives"]:
                    lines.append(f"    - {sc.get('nazovSk', 'N/A')} ({sc.get('kod', '')})")
                    # Funds
                    fond = sc.get("fond", {})
                    if fond:
                        lines.append(f"      Fund: {fond.get('nazovSk', 'N/A')}")
                lines.append("")

    return "\n".join(lines)
