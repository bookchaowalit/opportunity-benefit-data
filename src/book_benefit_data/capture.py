"""One explicit official source; all unsupported facts remain unknown."""

import argparse
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .cli import resource, validate
from .observability import init_sentry, report_exit


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, value):
        if not self.hidden:
            self.parts.append(value)


def _normalize_generic(raw, source, checked_at):
    if source.get("access") == "govuk-api":
        body = json.loads(raw)
        if not isinstance(body, dict) or not isinstance(body.get("details"), dict):
            raise ValueError("unexpected GOV.UK document")
        text = " ".join(str(body.get(key, "")) for key in ("title", "description", "details"))
    else:
        parser = Text()
        parser.feed(raw.decode("utf-8"))
        text = " ".join(" ".join(parser.parts).split())
    folded = text.casefold()
    markers = source.get("required_markers") or [source["title"]]
    if not all(marker.casefold() in folded for marker in markers):
        raise ValueError("generic benefit source drift or challenge page")
    schema = resource("schema-v2.json")
    terms: dict[str, Any] = {
        key: None for key in schema["properties"]["items"]["items"]["properties"]["terms"]["properties"]
    }
    terms.update(source.get("normalized_terms", {}))
    record_id = source["id"]
    item = {
        "id": record_id,
        "title": source["title"],
        "record_kind": source["record_kind"],
        "category": source["category"],
        "source_url": source["source_url"],
        "provider": source["provider"],
        "status": source.get("status", "unknown"),
        "deadline": {"kind": source.get("deadline_kind", "unknown"), "at": None},
        "availability": {"kind": source.get("availability_kind", "unknown"), "starts_at": None, "ends_at": None},
        "eligible_countries": source.get("eligible_countries", ["GLOBAL"]),
        "eligibility_text": source["eligibility_text"],
        "value": {
            "kind": source.get("value_kind", "unknown"),
            "amount": source.get("value_amount"),
            "currency": source.get("value_currency"),
            "guaranteed": source.get("value_guaranteed"),
        },
        "cost": {"fee_amount": None, "currency": None, "auto_renewal": None, "notes": source["cost_notes"]},
        "terms": terms,
        "related_records": [],
        "provenance": {
            "evidence_kind": "captured",
            "source_id": source["id"],
            "source_record_id": record_id,
            "checked_at": checked_at,
            "raw_object_key": None,
            "bronze_manifest_key": None,
        },
    }
    return {
        "schema_version": source["schema_version"],
        "source": source["product"],
        "retrieved_at": checked_at,
        "data_status": "live",
        "items": [item],
    }


def normalize(raw, source, checked_at):
    if source.get("generic_html"):
        return _normalize_generic(raw, source, checked_at)
    schema = resource("schema-v2.json")
    terms: dict[str, Any] = {
        key: None for key in schema["properties"]["items"]["items"]["properties"]["terms"]["properties"]
    }
    deadline: dict[str, Any] = {"kind": "unknown", "at": None}
    availability: dict[str, Any] = {"kind": "unknown", "starts_at": None, "ends_at": None}
    status = "unknown"
    countries: list[str] = []
    variants: list[dict[str, Any]] | None = None
    if source["access"] == "govuk-api":
        body = json.loads(raw)
        if not isinstance(body, dict):
            raise ValueError("unexpected GOV.UK document")
        if body.get("base_path") != source["source_url"].removeprefix("https://www.gov.uk") or not isinstance(
            body.get("details"), dict
        ):
            raise ValueError("unexpected GOV.UK document")
        title = body.get("title")
        expected = {"grant": "Apply for innovation funding", "benefit": "Universal Credit"}[source["domain"]]
        if title != expected:
            raise ValueError("source title drift")
        eligibility = (
            "UK program; read current eligibility and residence or organization requirements at the official source."
        )
        if source["domain"] == "benefit":
            terms["jurisdiction"] = "United Kingdom"
    elif source["id"] in {"thaigov-state-welfare-2569", "thaigov-water-support-2569"}:
        parser = Text()
        parser.feed(raw.decode("utf-8"))
        text = " ".join(" ".join(parser.parts).split())
        if source["id"] == "thaigov-state-welfare-2569":
            required = "โครงการสวัสดิการแห่งรัฐ ปี 2569" in text and "1 สิงหาคม 2569" in text and "1 ตุลาคม 2569" in text
            if not required:
                raise ValueError("Thai welfare source drift or challenge page")
        else:
            required = (
                "ลดค่าน้ำประปา" in text
                and "20 กรกฎาคม 2569" in text
                and "100 บาท" in text
                and "315 บาท" in text
                and "สวัสดิการแห่งรัฐ" in text
            )
            if not required:
                raise ValueError("Thai water-support source drift or challenge page")
        countries = ["TH"]
        status = "open"
        terms["jurisdiction"] = "Thailand"
        if source["id"] == "thaigov-state-welfare-2569":
            terms["beneficiary_group"] = "Thai state welfare card applicants who pass the published qualifications"
            terms["eligibility_evidence"] = (
                "Verify qualification results and identity verification through the official welfare channels."
            )
            terms["renewal_rule"] = "Benefits are credited on the published schedule; amounts and channels can change."
            eligibility = "Thai State Welfare Card 2569; published qualifications and identity verification apply before claiming benefits."
            variants = [
                {
                    "suffix": "existing",
                    "title": "Thai State Welfare Card 2569 — existing beneficiaries",
                    "availability": {"kind": "continuous", "starts_at": "2026-08-01T00:00:00Z", "ends_at": None},
                },
                {
                    "suffix": "new-or-reviewed",
                    "title": "Thai State Welfare Card 2569 — new or reviewed beneficiaries",
                    "availability": {"kind": "scheduled", "starts_at": "2026-10-01T00:00:00Z", "ends_at": None},
                },
            ]
        else:
            title = "Thai State Welfare Card 2569 — water-bill support"
            terms["beneficiary_group"] = (
                "Thai State Welfare Card 2569 beneficiaries who register the water-bill support"
            )
            terms["eligibility_evidence"] = (
                "Verify that the household passed the State Welfare Card 2569 qualification and complete the official water-support registration."
            )
            terms["renewal_rule"] = (
                "Support is applied per published water-billing cycle; one household or house number receives one entitlement."
            )
            eligibility = "State Welfare Card 2569 utility support; registration, household and billing conditions apply before the water-bill credit is applied."
            availability = {"kind": "continuous", "starts_at": "2026-07-20T00:00:00Z", "ends_at": None}
    else:
        raise ValueError("unknown benefit source")
    if variants is None:
        variants = [{"suffix": "", "title": title, "availability": availability}]
    items = []
    for variant in variants:
        record_id = (
            source["id"]
            + (":" + variant["suffix"] if variant["suffix"] else "")
            + (":" + deadline["at"][:10] if deadline["kind"] == "fixed" else "")
        )
        if source["id"] == "thaigov-water-support-2569":
            value = {"kind": "credit", "amount": 100, "currency": "THB", "guaranteed": False}
        else:
            value = {
                "kind": "variable"
                if source["id"] == "thaigov-state-welfare-2569"
                else ("access" if source["domain"] == "freebie" else "unknown"),
                "amount": None,
                "currency": None,
                "guaranteed": None,
            }
        item = {
            "id": record_id,
            "title": variant["title"],
            "record_kind": source["record_kind"],
            "category": source["category"],
            "source_url": source["source_url"],
            "provider": source["provider"],
            "status": status,
            "deadline": deadline,
            "availability": variant["availability"],
            "eligible_countries": countries,
            "eligibility_text": eligibility,
            "value": value,
            "cost": {
                "fee_amount": None,
                "currency": None,
                "auto_renewal": None,
                "notes": "Not extracted; review official terms before applying or claiming.",
            },
            "terms": dict(terms),
            "related_records": [],
            "provenance": {
                "evidence_kind": "captured",
                "source_id": source["id"],
                "source_record_id": record_id,
                "checked_at": checked_at,
                "raw_object_key": None,
                "bronze_manifest_key": None,
            },
        }
        items.append(item)
    return {
        "schema_version": source["schema_version"],
        "source": source["product"],
        "retrieved_at": checked_at,
        "data_status": "live",
        "items": items,
    }


def source_config(source_id=None):
    if source_id is None:
        return resource("source.json")
    if not re.fullmatch(r"[a-z0-9-]+", source_id):
        raise ValueError("invalid source id")
    base = resource("source.json")
    if base["id"] == source_id:
        return base
    try:
        return resource("source-" + source_id + ".json")
    except FileNotFoundError:
        raise ValueError("unknown source id") from None


def main(argv=None):
    selector = argparse.ArgumentParser(add_help=False)
    selector.add_argument("--source-id")
    selected, remaining = selector.parse_known_args(argv)
    root = os.environ.get("SOLO_DATA_LAKE_ROOT")
    if not root:
        print("Set SOLO_DATA_LAKE_ROOT to the local shared capture/lake runtime.", file=sys.stderr)
        return 2
    runtime = Path(root).resolve() / "infra/scripts"
    if not (runtime / "discovery/capture_runtime.py").is_file():
        print("Shared discovery runtime is unavailable.", file=sys.stderr)
        return 2
    sys.path.insert(0, str(runtime))
    from discovery.capture_runtime import VERSION, run

    if VERSION != 1:
        raise RuntimeError("unsupported shared capture runtime")
    source = source_config(selected.source_id)
    sentry = init_sentry(source["id"])
    return report_exit(sentry, source["id"], run(source, normalize, validate, remaining))


if __name__ == "__main__":
    raise SystemExit(main())
