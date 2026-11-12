

"""Fetch public career sources, validate conservative matches, track and alert."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import html
import json
import logging
import unicodedata
from email.utils import parsedate_to_datetime
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "jobs.json"
SOURCES_PATH = ROOT / "config" / "sources.json"
SITE_PATH = ROOT / "site" / "data" / "jobs.json"
HEADERS = {"User-Agent": "HoudiniJobHunter/1.0 (personal job monitor; public listings)", "Accept": "application/json,text/html;q=0.9,*/*;q=0.8"}
TIMEOUT = 18
LOG = logging.getLogger("jobwatch")

ROLE_STRONG = re.compile(r"\b(houdini|fx artist|fx lead|fx supervisor|effects supervisor|effects lead|effects artist|effects td|effects technical director|fx td|3d fx|3d effects|simulation(s)? (artist|td|engineer|developer|specialist)|procedural (?:\w+ ){0,2}(artist|td|modeler|modeller|designer|technical artist)|crowds? td)\b", re.I)
ROLE_MED = re.compile(r"\b(pipeline (td|technical director|engineer|developer)|technical artist|tech(nical)? animat(or|ion)|character fx|cfx|asset td|crowd(s)? (artist|supervisor)|rigging td|general td|render(ing)? td|houdini instructor|3d instructor|technical director|tools developer|technical developer|simulation(s)?|procedural generation|generative design|parametric design)\b", re.I)
ROLE_NO = re.compile(r"\b(2d fx|toon boom|harmony fx|cashier|accountant|retail|sales|business development|recruiter|human resources|product manager|finance|marketing|animator -|storyboard|compositor|motion editor|junior|intern(ship)?|apprentice(ship)?|trainee)\b", re.I)
ANIMATION_PROOF = re.compile(r"\b(feature animation|animated (film|feature|series|production|movie|show)|animation (feature|series|pipeline|studio|production)|fully animated|cgi animated|cg animated|cartoon|stylized animation|netflix animation studios|feature animated|walt disney animation|3d animation production)\b", re.I)
LIVE_ACTION_PROOF = re.compile(r"\b(live.action (film|series|vfx|production|show|work|project)|photoreal(istic)? live.action|on.set vfx|live.action plate)\b", re.I)
REMOTE = re.compile(r"\b(remote|work from home|work remotely|distributed|work from anywhere|fully remote)\b", re.I)
HYBRID = re.compile(r"\b(hybrid|on.site|in.office|onsite|on site|relocation required|must be located in|in.person)\b", re.I)
CANADA = re.compile(r"\b(canada|canadian|canada.wide|across canada|canadians|british columbia|\bbc\b|ontario|quebec|québec|vancouver|toronto|montreal|montréal|alberta|calgary|ottawa|winnipeg)\b", re.I)
VANCOUVER = re.compile(r"\b(vancouver|burnaby|richmond|new westminster|surrey|north vancouver|west vancouver|coquitlam|delta|port moody|port coquitlam|metro vancouver)\b", re.I)
US_ONLY = re.compile(r"\b(united states (only|remote|based)|us[- ]only|usa[- ]only|u\.s\. (residents|only|based)|must (reside|live|be located) in (the )?(usa|united states)|authorized to work in (the )?(u\.s\.|usa|united states))\b", re.I)
WORLDWIDE = re.compile(r"\b(worldwide|anywhere|global|globally|no location restrictions|any country)\b", re.I)
SALARY = re.compile(r'(?i)(?:CAD|CA\$|\$)\s*\d[\d,]*(?:\.\d+)?\s*(?:[-–—]|to)\s*(?:CAD|CA\$|\$)?\s*\d[\d,]*(?:\.\d+)?\s*(?:/(?:year|yr|hour|hr|week)|per (?:year|hour|week)|annually)?')
SIGNAL_TERMS = re.compile(r'(?i)\b(staffing up|hiring|recruitment|recruiting|greenlit|greenlight|new animated|animation slate|production begins|production underway|animation production|opens? (a )?(new )?studio|expansion|expanding|new series|new feature|renewed for|commissioned|new season)\b')
STUDIO_SIGNAL = re.compile(r'(?i)\b(animation|animated|studio|feature|series|fx|houdini|cgi|cg)\b')
EOI = re.compile(r"\b(expression of interest|general application|talent pool|evergreen)\b", re.I)


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def plain(value):
    if not value:
        return ""
    soup = BeautifulSoup(str(value), "html.parser")
    for el in soup(["script", "style", "nav", "footer", "header", "form"]):
        el.decompose()
    return re.sub(r"\s+", " ", html.unescape(soup.get_text(" ", strip=True))).strip()


def canonical_url(url):
    u = urlparse(url)
    return urlunparse((u.scheme, u.netloc.lower(), u.path.rstrip("/"), "", "", ""))


def job_id(source_id, raw_id=None, url=None):
    base = f"{source_id}:{raw_id or canonical_url(url or '')}"
    return hashlib.sha256(base.encode()).hexdigest()[:18]


def make_job(source, title, url, location="", description="", raw_id=None, posted_at=None, remote=False, company=None):
    return {
        "id": job_id(source["id"], raw_id, url), "source_id": source["id"],
        "company": company or source["name"], "title": plain(title)[:180],
        "url": url, "location": plain(location)[:300], "description": plain(description)[:16000],
        "posted_at": posted_at, "external_id": str(raw_id) if raw_id is not None else None,
        "remote": bool(remote), "studio": source["studio"], "source_label": source.get("source_label", "Official" if source["studio"] in ("animation", "mixed") else source["name"]), "source_kind": source["kind"]
    }


def http_get(url, session=None, **kwargs):
    session = session or requests
    resp = session.get(url, headers=HEADERS, timeout=TIMEOUT, **kwargs)
    resp.raise_for_status()
    return resp


def fetch_greenhouse(src, session=None):
    url = f'https://boards-api.greenhouse.io/v1/boards/{src["board"]}/jobs?content=true'
    data = http_get(url, session).json()
    if "jobs" not in data:
        raise ValueError("Greenhouse response missing jobs")
    jobs = []
    for item in data["jobs"]:
        if item.get("internal_job_id") is None:  # generic prospect / EOI post
            continue




