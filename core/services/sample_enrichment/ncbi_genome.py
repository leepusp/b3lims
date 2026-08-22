import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from django.db import transaction

from core.models.samples.enrichment import (
    EXTERNAL_SOURCE_NCBI,
    SampleEnrichmentSnapshot,
    SampleExternalIdentifier,
    SampleGenomeAssemblyAssignment,
)


NCBI_DATASETS_VERSION = "datasets-v2"

NCBI_GENOME_BASE_URL = (
    "https://api.ncbi.nlm.nih.gov/"
    "datasets/v2/genome/accession"
)

NCBI_USER_AGENT = (
    "DaVinci-Biobank/"
    "sample-genome-assembly-enrichment-v1"
)

ASSEMBLY_ACCESSION_RE = re.compile(
    r"^(?:GCF|GCA)_\d{9}\.\d+$"
)


class NCBIGenomeLookupError(RuntimeError):
    pass


def _canonical_json_bytes(payload):
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
    ).encode("utf-8")


def _payload_checksum(payload):
    return hashlib.sha256(
        _canonical_json_bytes(payload)
    ).hexdigest()


def normalize_assembly_accession(accession):
    value = (
        str(accession or "")
        .strip()
        .upper()
    )

    if not ASSEMBLY_ACCESSION_RE.fullmatch(
        value
    ):
        raise ValueError(
            "Enter an explicit versioned NCBI "
            "Assembly accession in GCF_#########.# "
            "or GCA_#########.# format."
        )

    return value


def build_ncbi_genome_url(accession):
    normalized = normalize_assembly_accession(
        accession
    )

    encoded = urllib.parse.quote(
        normalized,
        safe="",
    )

    return (
        f"{NCBI_GENOME_BASE_URL}/"
        f"{encoded}/dataset_report"
    )


def _network_url(base_url):
    api_key = (
        os.environ
        .get(
            "NCBI_API_KEY",
            "",
        )
        .strip()
    )

    if not api_key:
        return base_url

    separator = (
        "&"
        if "?" in base_url
        else "?"
    )

    return (
        base_url
        + separator
        + "api_key="
        + urllib.parse.quote(
            api_key,
            safe="",
        )
    )


def _fetch_ncbi_genome_payload(public_url):
    request = urllib.request.Request(
        _network_url(public_url),
        headers={
            "Accept": "application/json",
            "User-Agent": NCBI_USER_AGENT,
        },
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=20,
        ) as response:
            status = int(
                getattr(
                    response,
                    "status",
                    200,
                )
                or 200
            )

            payload = json.load(response)

    except urllib.error.HTTPError as exc:
        raise NCBIGenomeLookupError(
            "NCBI returned HTTP "
            f"{exc.code}."
        ) from exc

    except urllib.error.URLError as exc:
        raise NCBIGenomeLookupError(
            "Could not reach NCBI: "
            f"{exc.reason}"
        ) from exc

    except TimeoutError as exc:
        raise NCBIGenomeLookupError(
            "NCBI request timed out."
        ) from exc

    except json.JSONDecodeError as exc:
        raise NCBIGenomeLookupError(
            "NCBI returned invalid JSON."
        ) from exc

    if not isinstance(payload, dict):
        raise NCBIGenomeLookupError(
            "NCBI returned an unexpected "
            "response type."
        )

    return payload, status


def _clean_string(value):
    return str(
        value or ""
    ).strip()


def _accession_value(value):
    if isinstance(value, dict):
        return _clean_string(
            value.get("accession")
        )

    return _clean_string(value)


def _positive_int(value):
    if value in (
        None,
        "",
    ):
        return None

    try:
        result = int(value)
    except (
        TypeError,
        ValueError,
    ):
        return None

    if result < 0:
        return None

    return result


def _float_value(value):
    if value in (
        None,
        "",
    ):
        return None

    try:
        return float(value)
    except (
        TypeError,
        ValueError,
    ):
        return None


def normalize_ncbi_genome_payload(payload):
    reports = (
        payload.get("reports")
        or []
    )

    if not isinstance(reports, list):
        reports = []

    total_count = payload.get(
        "total_count"
    )

    if len(reports) == 0:
        return {
            "resolution_status": "not_found",
            "result_count": 0,
            "total_count": total_count,
        }

    if len(reports) != 1:
        return {
            "resolution_status": "ambiguous",
            "result_count": len(reports),
            "total_count": total_count,
        }

    report = reports[0]

    if not isinstance(report, dict):
        return {
            "resolution_status": "unresolved",
            "result_count": 1,
            "total_count": total_count,
        }

    organism = (
        report.get("organism")
        or {}
    )

    if not isinstance(organism, dict):
        organism = {}

    assembly_info = (
        report.get("assembly_info")
        or {}
    )

    if not isinstance(
        assembly_info,
        dict,
    ):
        assembly_info = {}

    assembly_stats = (
        report.get("assembly_stats")
        or {}
    )

    if not isinstance(
        assembly_stats,
        dict,
    ):
        assembly_stats = {}

    biosample = (
        report.get("biosample")
        or {}
    )

    if isinstance(biosample, list):
        biosample = (
            biosample[0]
            if biosample
            and isinstance(
                biosample[0],
                dict,
            )
            else {}
        )

    if not isinstance(biosample, dict):
        biosample = {}

    accession = _accession_value(
        report.get("accession")
    )

    current_accession = (
        _accession_value(
            report.get(
                "current_accession"
            )
        )
        or accession
    )

    paired_accession = (
        _accession_value(
            report.get(
                "paired_accession"
            )
        )
        or _accession_value(
            assembly_info.get(
                "paired_assembly"
            )
        )
    )

    raw_tax_id = organism.get(
        "tax_id"
    )

    taxon_id = (
        str(raw_tax_id)
        if raw_tax_id is not None
        else ""
    )

    biosample_accession = (
        _accession_value(
            assembly_info.get(
                "biosample_accession"
            )
        )
        or _accession_value(
            biosample.get(
                "accession"
            )
        )
    )

    normalized = {
        "resolution_status": (
            "resolved"
            if accession
            else "unresolved"
        ),
        "result_count": 1,
        "total_count": total_count,
        "accession": accession,
        "current_accession": (
            current_accession
        ),
        "paired_accession": (
            paired_accession
        ),
        "source_database": (
            _clean_string(
                report.get(
                    "source_database"
                )
            )
        ),
        "organism_name": (
            _clean_string(
                organism.get(
                    "organism_name"
                )
            )
        ),
        "taxon_id": taxon_id,
        "assembly_name": (
            _clean_string(
                assembly_info.get(
                    "assembly_name"
                )
            )
        ),
        "assembly_level": (
            _clean_string(
                assembly_info.get(
                    "assembly_level"
                )
            )
        ),
        "assembly_status": (
            _clean_string(
                assembly_info.get(
                    "assembly_status"
                )
            )
        ),
        "assembly_type": (
            _clean_string(
                assembly_info.get(
                    "assembly_type"
                )
            )
        ),
        "refseq_category": (
            _clean_string(
                assembly_info.get(
                    "refseq_category"
                )
            )
        ),
        "release_date": (
            _clean_string(
                assembly_info.get(
                    "release_date"
                )
            )
        ),
        "submitter": (
            _clean_string(
                assembly_info.get(
                    "submitter"
                )
            )
        ),
        "bioproject_accession": (
            _accession_value(
                assembly_info.get(
                    "bioproject_accession"
                )
            )
        ),
        "biosample_accession": (
            biosample_accession
        ),
        "total_sequence_length": (
            _positive_int(
                assembly_stats.get(
                    "total_sequence_length"
                )
            )
        ),
        "number_of_contigs": (
            _positive_int(
                assembly_stats.get(
                    "number_of_contigs"
                )
            )
        ),
        "number_of_scaffolds": (
            _positive_int(
                assembly_stats.get(
                    "number_of_scaffolds"
                )
            )
        ),
        "contig_n50": (
            _positive_int(
                assembly_stats.get(
                    "contig_n50"
                )
            )
        ),
        "scaffold_n50": (
            _positive_int(
                assembly_stats.get(
                    "scaffold_n50"
                )
            )
        ),
        "gc_percent": (
            _float_value(
                assembly_stats.get(
                    "gc_percent"
                )
            )
        ),
    }

    return normalized


def _snapshot_error_message(normalized):
    status = normalized.get(
        "resolution_status"
    )

    if status == "not_found":
        return (
            "NCBI did not return a Genome "
            "Assembly record for this accession."
        )

    if status == "ambiguous":
        return (
            "NCBI returned multiple Genome "
            "Assembly records for one accession."
        )

    if status != "resolved":
        return (
            "NCBI Genome Assembly response "
            "could not be normalized."
        )

    return ""


def resolve_and_store_ncbi_genome_assembly(
    sample,
    user,
    accession,
):
    query = normalize_assembly_accession(
        accession
    )

    public_url = build_ncbi_genome_url(
        query
    )

    try:
        payload, http_status = (
            _fetch_ncbi_genome_payload(
                public_url
            )
        )

    except NCBIGenomeLookupError as exc:
        empty_payload = {}

        SampleEnrichmentSnapshot.objects.create(
            sample=sample,
            source=EXTERNAL_SOURCE_NCBI,
            query=query,
            request_url=public_url,
            source_version=NCBI_DATASETS_VERSION,
            source_record_id=query,
            http_status=None,
            success=False,
            error_message=str(exc),
            raw_payload=empty_payload,
            normalized_payload={
                "resolution_status": "error",
            },
            checksum_sha256=(
                _payload_checksum(
                    empty_payload
                )
            ),
            requested_by=user,
        )

        raise

    normalized = (
        normalize_ncbi_genome_payload(
            payload
        )
    )

    resolution_status = (
        normalized.get(
            "resolution_status"
        )
    )

    success = (
        resolution_status == "resolved"
    )

    error_message = (
        _snapshot_error_message(
            normalized
        )
    )

    with transaction.atomic():
        snapshot = (
            SampleEnrichmentSnapshot.objects
            .create(
                sample=sample,
                source=EXTERNAL_SOURCE_NCBI,
                query=query,
                request_url=public_url,
                source_version=NCBI_DATASETS_VERSION,
                source_record_id=(
                    normalized.get(
                        "accession"
                    )
                    or query
                ),
                http_status=http_status,
                success=success,
                error_message=error_message,
                raw_payload=payload,
                normalized_payload=normalized,
                checksum_sha256=(
                    _payload_checksum(
                        payload
                    )
                ),
                requested_by=user,
            )
        )

        assignment = None

        if success:
            resolved_accession = (
                normalized[
                    "accession"
                ]
            )

            previous = (
                SampleGenomeAssemblyAssignment
                .objects
                .filter(
                    sample=sample,
                    source=EXTERNAL_SOURCE_NCBI,
                    accession=resolved_accession,
                )
                .first()
            )

            match_status = (
                SampleGenomeAssemblyAssignment
                .STATUS_CANDIDATE
            )

            reviewed_by = None
            reviewed_at = None

            if (
                previous is not None
                and previous.match_status
                in {
                    SampleGenomeAssemblyAssignment
                    .STATUS_VERIFIED,
                    SampleGenomeAssemblyAssignment
                    .STATUS_CONFLICT,
                }
            ):
                # Refreshing the same Assembly accession must not
                # erase a prior human review decision.
                match_status = (
                    previous.match_status
                )

                reviewed_by = (
                    previous.reviewed_by
                )

                reviewed_at = (
                    previous.reviewed_at
                )

            (
                SampleGenomeAssemblyAssignment
                .objects
                .filter(
                    sample=sample,
                    source=EXTERNAL_SOURCE_NCBI,
                    is_current=True,
                )
                .exclude(
                    accession=resolved_accession
                )
                .update(
                    is_current=False
                )
            )

            defaults = {
                key: normalized.get(key)
                for key in (
                    "current_accession",
                    "paired_accession",
                    "source_database",
                    "organism_name",
                    "taxon_id",
                    "assembly_name",
                    "assembly_level",
                    "assembly_status",
                    "assembly_type",
                    "refseq_category",
                    "release_date",
                    "submitter",
                    "bioproject_accession",
                    "biosample_accession",
                    "total_sequence_length",
                    "number_of_contigs",
                    "number_of_scaffolds",
                    "contig_n50",
                    "scaffold_n50",
                    "gc_percent",
                )
            }

            defaults.update(
                {
                    "match_status": (
                        match_status
                    ),
                    "is_current": True,
                    "snapshot": snapshot,
                    "reviewed_by": (
                        reviewed_by
                    ),
                    "reviewed_at": (
                        reviewed_at
                    ),
                }
            )

            (
                assignment,
                _,
            ) = (
                SampleGenomeAssemblyAssignment
                .objects
                .update_or_create(
                    sample=sample,
                    source=EXTERNAL_SOURCE_NCBI,
                    accession=resolved_accession,
                    defaults=defaults,
                )
            )

            (
                SampleExternalIdentifier
                .objects
                .filter(
                    sample=sample,
                    source=EXTERNAL_SOURCE_NCBI,
                    identifier_type=(
                        "assembly_accession"
                    ),
                )
                .update(
                    is_primary=False
                )
            )

            identifier_values = [
                (
                    "assembly_accession",
                    resolved_accession,
                    True,
                ),
                (
                    "paired_assembly_accession",
                    normalized.get(
                        "paired_accession"
                    ),
                    False,
                ),
                (
                    "bioproject",
                    normalized.get(
                        "bioproject_accession"
                    ),
                    False,
                ),
                (
                    "biosample",
                    normalized.get(
                        "biosample_accession"
                    ),
                    False,
                ),
            ]

            for (
                identifier_type,
                identifier,
                is_primary,
            ) in identifier_values:
                value = _clean_string(
                    identifier
                )

                if not value:
                    continue

                (
                    SampleExternalIdentifier
                    .objects
                    .update_or_create(
                        sample=sample,
                        source=EXTERNAL_SOURCE_NCBI,
                        identifier_type=(
                            identifier_type
                        ),
                        identifier=value,
                        defaults={
                            "is_primary": (
                                is_primary
                            ),
                        },
                    )
                )

    return {
        "snapshot": snapshot,
        "assignment": assignment,
        "normalized": normalized,
    }
