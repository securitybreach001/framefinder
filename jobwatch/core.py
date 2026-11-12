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
        loc = item.get("location") or {}
        dept = ", ".join(d.get("name", "") for d in item.get("departments") or [])
        description = (item.get("content") or "") + " " + dept
        jobs.append(make_job(src, item.get("title", ""), item.get("absolute_url", ""), loc.get("name", ""),
                             description, raw_id=item.get("id"), posted_at=None))  # updated_at != posted date
    return jobs


def fetch_lever(src, session=None):
    raw = http_get(f'https://api.lever.co/v0/postings/{src["board"]}?mode=json', session).json()
    if not isinstance(raw, list):
        raise ValueError("Lever response should be a list")
    jobs = []
    for x in raw:
        cats = x.get("categories") or {}
        loc = cats.get("location", "")
        desc = " ".join([x.get("descriptionPlain", ""), x.get("additionalPlain", ""),
                          cats.get("team", ""), cats.get("commitment", "")])
        jobs.append(make_job(src, x.get("text", ""), x.get("hostedUrl") or x.get("applyUrl", ""), loc,
                             desc, raw_id=x.get("id"), remote=(cats.get("workplaceType", "") == "remote")))
    return jobs


def fetch_ashby(src, session=None):
    data = http_get(f'https://api.ashbyhq.com/posting-api/job-board/{src["board"]}?includeCompensation=true', session).json()
    if "jobs" not in data:
        raise ValueError("Ashby response missing jobs")
    jobs=[]
    for x in data["jobs"]:
        if not x.get("isListed", True):
            continue
        loc = "; ".join([x.get("location") or ""] + [l.get("location", "") for l in (x.get("secondaryLocations") or [])]).strip("; ")
        jobs.append(make_job(src, x.get("title", ""), x.get("jobUrl") or x.get("applyUrl", ""), loc,
                             x.get("descriptionPlain") or x.get("descriptionHtml"),
                             raw_id=x.get("id") or x.get("jobUrl"), posted_at=x.get("publishedAt"),
                             remote=x.get("isRemote", False)))
    return jobs


def fetch_eightfold(src, session=None):
    """Read Netflix's public Eightfold jobs endpoint (undocumented, may change)."""
    host=src['host'].rstrip('/')
    domain=src['domain']
    jobs=[]
    # The classic API limits the page size to 10 even when a larger value is requested.
    for start in range(0, 500, 10):
        data=http_get(f'{host}/api/apply/v2/jobs',session,params={
            'domain':domain,'start':start,'num':10
        }).json()
        rows=data.get('positions') or []
        if not isinstance(rows,list):raise ValueError('Eightfold jobs response is not an array')
        if not rows:break
        for x in rows:
            title=x.get('name') or x.get('posting_name') or x.get('title') or ''
            if not potential_role(title):continue
            loc=x.get('location') or x.get('primaryLocation') or x.get('primary_location') or ''
            if isinstance(loc,dict):loc=', '.join(v for v in [loc.get('city'),loc.get('state'),loc.get('country')] if v)
            if isinstance(loc,list):loc='; '.join(str(v) for v in loc)
            loc=str(loc)
            dept=' '.join(str(x.get(k) or '') for k in ['department','team','category','businessUnit','business_unit'])
            desc=' '.join([dept,str(x.get('job_description') or x.get('jobDescription') or '')])
            rid=x.get('id') or x.get('position_id')
            url=x.get('canonicalPositionUrl') or x.get('canonical_position_url') or x.get('positionUrl') or x.get('position_url') or f'/careers/job/{rid}'
            url=urljoin(host,url)
            jobs.append(make_job(src,title,url,loc,desc,raw_id=rid or url,
                                 remote=bool(REMOTE.search(loc))))
        if len(rows)<10 or start+len(rows)>=int(data.get('count') or 0):break
    # Retrieve details only when the listing itself lacks project/team evidence.
    candidates=dedupe_jobs(jobs)
    return enrich_candidate_details(candidates,session)


def fetch_jazzhr(src, session=None):
    page = http_get(src["url"], session)
    soup = BeautifulSoup(page.text, "html.parser")
    candidates=[]
    for a in soup.select("a[href]"):
        url=urljoin(page.url, a.get("href", ""))
        if not re.search(r"/apply/[A-Za-z0-9]{5,}/[^?#]+", url):
            continue
        title=a.get_text(" ",strip=True)
        if not title or len(title)>180:
            continue
        near=plain(a.parent.parent.get_text(" ",strip=True))[:350] if a.parent and a.parent.parent else ""
        candidates.append(make_job(src,title,url,near or src.get("default_location", ""),""))
    return enrich_candidate_details(dedupe_jobs(candidates), session)


def fetch_bamboohr(src, session=None):
    base=f'https://{src["board"]}.bamboohr.com'
    data=http_get(base+'/careers/list',session).json()
    if not isinstance(data.get("result"),list):
        raise ValueError("BambooHR response missing result array")
    jobs=[]
    for x in data['result']:
        title=x.get('jobOpeningName','')
        if not potential_role(title):
            continue
        ident=x.get('id')
        detail=http_get(f'{base}/careers/{ident}/detail',session).json().get('result',{}).get('jobOpening',{})
        loc=detail.get('location') or x.get('location') or {}
        location=', '.join(v for v in [loc.get('city'),loc.get('state') or loc.get('province'),loc.get('addressCountry')] if v)
        jobs.append(make_job(src,title,detail.get('jobOpeningShareUrl') or f'{base}/careers/{ident}',
                             location,detail.get('description',''),raw_id=ident,posted_at=detail.get('datePosted'),
                             remote=x.get('isRemote') is True))
    return jobs


def fetch_workable(src, session=None):
    """Uses public board widget; vendor can change schema without warning."""
    base=f'https://apply.workable.com/{src["board"]}/'
    sess=session or requests
    candidates=[]
    # Public widget JSON, not the employer's authenticated SPI API.
    try:
        data=http_get(f'https://apply.workable.com/api/v1/widget/accounts/{src["board"]}?details=true',sess).json()
        if isinstance(data, dict):
            rows=data.get('jobs') or data.get('results') or data.get('openings') or []
        elif isinstance(data,list):
            rows=data
        else:
            rows=[]
        for x in rows:
            loc=x.get('location') or x.get('locations') or ''
            if isinstance(loc,dict): loc=', '.join(str(v) for v in loc.values() if isinstance(v,(str,int)))
            if isinstance(loc,list): loc='; '.join(l.get('name',str(l)) if isinstance(l,dict) else str(l) for l in loc)
            slug=x.get('shortcode') or x.get('id') or x.get('code') or ''
            url=x.get('url') or (base+'j/'+str(slug)+'/')
            candidates.append(make_job(src,x.get('title') or x.get('name'),url,loc,
                                      x.get('description') or x.get('descriptionText') or '',raw_id=slug or url,
                                      remote=x.get('remote') is True))
    except (ValueError,requests.RequestException) as exc:
        LOG.warning('%s public widget unavailable: %s, trying HTML',src['id'],exc)
    if candidates:
        return enrich_candidate_details(dedupe_jobs(candidates),session)
    # Fall back to visible HTML links, if the widget changes.
    copy=dict(src,kind='html',url=base)
    return fetch_html(copy,session)


def html_candidates(soup, base, src):
    jobs=[]
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            tree=json.loads(script.string or script.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        def walk(x):
            if isinstance(x,list):
                for child in x: yield from walk(child)
            elif isinstance(x,dict):
                typ=x.get('@type','')
                if typ=='JobPosting' or (isinstance(typ,list) and 'JobPosting' in typ): yield x
                for v in x.values():
                    if isinstance(v,(list,dict)): yield from walk(v)
        for x in walk(tree):
            loc=x.get('jobLocation') or []
            if isinstance(loc,dict):loc=[loc]
            locations=[]
            for item in loc:
                addr=item.get('address') or {}
                if isinstance(addr,dict):
                    locations.append(', '.join(str(addr[k]) for k in ('addressLocality','addressRegion','addressCountry') if addr.get(k)))
            url=x.get('url') or x.get('sameAs') or base
            jobs.append(make_job(src,x.get('title'),url, '; '.join(locations),x.get('description'),
                                 raw_id=x.get('identifier',{}).get('value') if isinstance(x.get('identifier'),dict) else None,
                                 posted_at=x.get('datePosted'),remote=str(x.get('jobLocationType','')).upper()=='TELECOMMUTE'))
    for a in soup.select('a[href]'):
        title=re.sub(r'\s+',' ',a.get_text(' ',strip=True))
        if not potential_role(title):
            continue
        href=urljoin(base,a.get('href',''))
        if not href.startswith('http') or href==base or href.startswith('mailto:'):
            continue
        # Only links that look like a specific application/job posting (or link from career listing).
        near=plain(a.parent.parent.get_text(' ',strip=True))[:300] if a.parent and a.parent.parent else ''
        jobs.append(make_job(src,title,href,near or src.get('default_location',''),''))
    return dedupe_jobs(jobs)


def fetch_html(src, session=None):
    resp=http_get(src['url'],session)
    soup=BeautifulSoup(resp.text,'html.parser')
    candidates=html_candidates(soup,resp.url,src)
    if not candidates:
        content=plain(resp.text).lower()
        if src.get('empty_message') and src['empty_message'] in content:
            return []
        raise ValueError('No parseable job links. This page may require JavaScript or a new adapter.')
    return enrich_candidate_details(candidates,session)


def enrich_candidate_details(candidates, session=None):
    """Fetch only candidate titles to avoid crawling an entire careers board."""
    result=[]
    for job in candidates:
        if not potential_role(job['title']):
            continue
        if job.get('description') and len(job['description'])>280:
            result.append(job); continue
        try:
            resp=http_get(job['url'],session)
            soup=BeautifulSoup(resp.text,'html.parser')
            main=soup.find('main') or soup.find('article') or soup.body or soup
            for tag in main(['script','style','nav','header','footer','form']):tag.decompose()
            description=main.get_text(' ',strip=True)
            job['description']=re.sub(r'\s+',' ',description)[:16000]
            # Only infer the location from the header of an individual job page, not the whole site.
            header=job['description'][:420]
            if VANCOUVER.search(header): job['location']='Vancouver, BC, Canada'
        except requests.RequestException as exc:
            LOG.warning('Detail fetch failed %s: %s',job['url'],exc)
        result.append(job)
    return result


def fetch_jobicy(src, session=None):
    data=http_get('https://jobicy.com/api/jobs',session,params={'count':100,'tag':src['tag']}).json()
    if data.get('success') is False or not isinstance(data.get('jobs'),list):
        raise ValueError('Jobicy returned invalid response')
    return [make_job(src,x.get('jobTitle'),x.get('url',''),x.get('jobGeo',''),
                     x.get('jobDescription') or x.get('jobExcerpt',''),raw_id=x.get('id'),
                     posted_at=x.get('pubDate'),remote=True,company=x.get('companyName') or src['name'])
            for x in data['jobs']]


def fetch_rss_signals(src, session=None):
    """Public RSS discovery of early hiring indicators. Not job listings."""
    import xml.etree.ElementTree as ET
    response=http_get(src['url'],session)
    root=ET.fromstring(response.content if hasattr(response,'content') else response.text)
    items=[]
    for node in root.findall('.//item')[:35]:
        title=plain(node.findtext('title') or '')
        url=(node.findtext('link') or '').strip()
        snippet=plain(node.findtext('description') or '')
        date=node.findtext('pubDate')
        if not (title and url and SIGNAL_TERMS.search(title+' '+snippet[:250]) and STUDIO_SIGNAL.search(title+' '+snippet[:250])):
            continue
        try: dt=parsedate_to_datetime(date).astimezone(timezone.utc).isoformat() if date else None
        except (TypeError, ValueError): dt=None
        ident=hashlib.sha256(canonical_url(url).encode()).hexdigest()[:18]
        items.append({'id':ident,'title':title[:220],'url':url,'summary':snippet[:350],
                      'company':src['name'],'signal_type':'Public production / hiring news',
                      'published_at':dt,'source':src['name'],'first_seen':utc_now()})
    return items


def normalized_words(s):
    s=unicodedata.normalize('NFKD',str(s)).encode('ascii','ignore').decode().lower()
    s=re.sub(r'\b(senior|sr|intermediate|mid|junior|jr|lead)\b', lambda m:m.group(0), s)
    return re.sub(r'[^a-z0-9]+',' ',s).strip()


def group_key(j):
    # Same actual title/company: location is not part of the key so the same remote
    # role advertised with alternate geographic labels remains one opportunity.
    company=normalized_words(j.get('company',''))
    company=re.sub(r'\b(inc|ltd|limited|studios|studio|creative lab|entertainment|animation)\b','',company).strip()
    return company+'|'+normalized_words(j.get('title',''))


def guess_arrangement(j):
    location=j.get('location',''); desc=j.get('description','')[:1800]
    label=location+' '+desc
    if re.search(r'(?i)\bhybrid\b', label):return 'Hybrid'
    if j.get('remote') or re.search(r'(?i)\b(fully remote|100% remote|remote[- ]first|work remotely)\b',label):return 'Remote'
    if re.search(r'(?i)\b(on[- ]site|onsite|in.person|in.office)\b',label):return 'On-site'
    return 'Not specified'


def salary_hint(j):
    # Source provided salary preferred; otherwise literal quoted ranges in job text.
    if j.get('salary'):return str(j['salary'])[:90]
    m=SALARY.search(j.get('description','')[:8000]);return m.group(0)[:90] if m else 'Not listed'


def grouped_jobs(jobs):
    """Stable cross-board identity; show all verified posting URLs, never fake ad presence."""
    groups={}
    for j in sorted(jobs,key=lambda x:(x.get('tier')=='match',x.get('score',0),x.get('source_label')=='Official'),reverse=True):
        k=group_key(j)
        if not k.strip('|'):continue
        if k not in groups:
            logical_id=hashlib.sha256(k.encode()).hexdigest()[:18]
            groups[k]={**j,'id':logical_id,'original_ids':[j['id']],'sources':[],
                       'salary':salary_hint(j),'arrangement':guess_arrangement(j)}
        else:
            target=groups[k]
            target['original_ids'].append(j['id'])
            target['first_seen']=min(target.get('first_seen',''),j.get('first_seen',''))
            if target.get('salary','Not listed')=='Not listed' and salary_hint(j)!='Not listed':target['salary']=salary_hint(j)
            if target.get('arrangement')=='Not specified' and guess_arrangement(j)!='Not specified':target['arrangement']=guess_arrangement(j)
            if j.get('location') and j['location'] not in target.get('location','') and target.get('arrangement')=='Remote':
                target['location']=target['location'] or j['location']
        source={'label':j.get('source_label') or j.get('company','Source'),
                'url':j['url'],'kind':j.get('source_kind','html')}
        if source not in groups[k]['sources']:groups[k]['sources'].append(source)
    for j in groups.values():
        j['sources'].sort(key=lambda x:(x['label']!='Official',x['label']))
        if j['sources']:
            official=next((x for x in j['sources'] if x['label']=='Official'),j['sources'][0]);j['url']=official['url']
    return list(groups.values())



def fetch_remotive(src,session=None):
    data=http_get('https://remotive.com/api/remote-jobs',session,params={'search':src.get('search','houdini')}).json()
    if not isinstance(data.get('jobs'),list):raise ValueError('Remotive jobs absent')
    return [make_job(src,x.get('title',''),x.get('url',''),x.get('candidate_required_location',''),
                     x.get('description',''),raw_id=x.get('id'),posted_at=x.get('publication_date'),
                     remote=True,company=x.get('company_name') or 'Unknown') for x in data['jobs']]


def fetch_arbeitnow(src,session=None):
    data=http_get('https://www.arbeitnow.com/api/job-board-api',session).json()
    if not isinstance(data.get('data'),list):raise ValueError('Arbeitnow data absent')
    return [make_job(src,x.get('title',''),x.get('url',''),x.get('location',''),x.get('description',''),
                     raw_id=x.get('slug'),remote=bool(x.get('remote')),company=x.get('company_name') or 'Unknown')
            for x in data['data'] if potential_role(x.get('title',''))]

def dedupe_jobs(jobs):
    d={}
    for j in jobs:
        if not j.get('title') or not j.get('url'):continue
        d[j['id']]=j
    return list(d.values())


def potential_role(title):
    return bool(ROLE_STRONG.search(title) or ROLE_MED.search(title)) and not bool(ROLE_NO.search(title) and not re.search(r'houdini',title,re.I))


def analyze(job):
    title=job['title']; description=job.get('description',''); loc=job.get('location','')
    # This is intentionally conservative: false negatives are listed in review, not pushed.
    reasons=[]
    if not potential_role(title):
        return 'excluded',0,['Unrelated role title']
    high=bool(ROLE_STRONG.search(title)); score=92 if high else 72
    reasons.append('Core Houdini/FX role' if high else 'Adjacent technical/procedural role')
    if EOI.search(title):
        return 'review', 45, ['Expression of interest, not a confirmed opening']
    if LIVE_ACTION_PROOF.search(title+' '+description[:1800]):
        return 'excluded',0,['Explicit live-action VFX project']
    studio=job.get('studio','other')
    if studio=='mixed':
        # Studio-level boilerplate mentions animation AND live-action; require a role/team-specific indicator.
        project=(title+' '+description[:900]).lower()
        proof=bool(ANIMATION_PROOF.search(project))
        if not proof:
            return 'review',min(score,55),['Mixed VFX/animation studio; animated production not confirmed']
        reasons.append('Animated project/team specifically indicated')
    elif studio=='animation':
        reasons.append('Animation-focused studio')
    else:
        reasons.append('Non-entertainment / adjacent opportunity')
    location=loc.lower(); body=description[:2800].lower()
    if US_ONLY.search(location+' '+body[:1000]) and not CANADA.search(body[:600]):
        return 'excluded',0,['US-only work eligibility; Canada not accepted']
    if VANCOUVER.search(location):
        reasons.append('Vancouver / Metro Vancouver')
    elif WORLDWIDE.search(location) and (job.get('remote') or REMOTE.search(location)):
        if HYBRID.search(body[:350]) and not re.search(r'fully remote',body[:350]):
            return 'review',55,['Worldwide remote label conflicts with hybrid/on-site wording']
        reasons.append('Worldwide remote')
    elif CANADA.search(location):
        if job.get('remote') or (REMOTE.search(location) and not HYBRID.search(location)):
            if HYBRID.search(body[:700]) and not re.search(r'fully remote',body[:700]):
                return 'review',55,['Canadian remote label conflicts with hybrid wording']
            reasons.append('Remote within Canada')
        elif re.search(r'fully remote|100% remote|work remotely (from|across|in) canada',body[:1400]):
            reasons.append('Remote within Canada')
        else:
            return 'review',58,['Outside Vancouver; fully remote work not verified']
    elif location and re.search(r'\b(united states|usa|u\.s\.|california|new york|los angeles|seattle|burbank|san francisco)\b',location):
        if (job.get('remote') or REMOTE.search(location)) and (CANADA.search(body[:1400]) or WORLDWIDE.search(body[:1400])) and not US_ONLY.search(body[:1400]):
            reasons.append('US employer explicitly open to Canada/worldwide remote')
        else:
            return 'excluded',0,['US-based role lacks explicit eligibility for working from Canada']
    elif job.get('remote') and re.search(r'\b(canada|worldwide|anywhere)\b',location+' '+body[:1000]):
        reasons.append('Remote with Canada/worldwide eligibility')
    else:
        return 'review',55,['Location or Canada remote eligibility not verified']
    if re.search(r'\b(temporary|freelance|contract)\b',title,re.I):score-=3
    return 'match',min(score,99),reasons


def load_state(path=STATE_PATH):
    if not Path(path).exists(): return {'version':1,'last_run':None,'sources':{},'jobs':{}}
    d=json.loads(Path(path).read_text(encoding='utf-8'))
    d.setdefault('sources',{});d.setdefault('jobs',{});return d


def merge_state(state, source_results, now):
    """Keep full seen-history; only close jobs after a successful NON-aggregator fetch."""
    new=[]; successful=[]
    for src, jobs, error in source_results:
        sid=src['id']
        page=src.get('url') or {
            'greenhouse': f'https://job-boards.greenhouse.io/{src.get("board", "")}',
            'lever': f'https://jobs.lever.co/{src.get("board", "")}',
            'ashby': f'https://jobs.ashbyhq.com/{src.get("board", "")}',
            'bamboohr': f'https://{src.get("board", "")}.bamboohr.com/careers',
            'workable': f'https://apply.workable.com/{src.get("board", "")}/',
            'eightfold': src.get('host','') + '/careers',
            'jobicy': 'https://jobicy.com/jobs-rss-feed',
            'rss_signal': src.get('url',''), 'remotive':'https://remotive.com/remote-jobs',
            'arbeitnow':'https://www.arbeitnow.com/'
        }.get(src['kind'], '')
        stamp={'name':src['name'],'kind':src['kind'],'url':page,
                              'last_checked':now, 'status':'error' if error else 'ok', 'count':len(jobs),
                              'message':str(error)[:240] if error else src.get('note','')}
        state['sources'][sid]=stamp
        if error: continue
        successful.append(sid)
        if src['kind']=='rss_signal':
            for signal in jobs:
                sid2=signal['id'];previous=state['signals'].get(sid2,{})
                state['signals'][sid2]={**signal,'first_seen':previous.get('first_seen',now),'notified':previous.get('notified',False)}
            continue
        seen=set()
        for job in jobs:
            if not job.get('url') or not job.get('title'):continue
            tier,score,reasons=analyze(job)
            if tier=='excluded':continue
            jid=job['id'];seen.add(jid)
            existing=state['jobs'].get(jid,{})
            record={**existing,**job,'tier':tier,'score':score,'reasons':reasons,
                    'first_seen':existing.get('first_seen',now),'last_seen':now,'active':True,
                    'notified':existing.get('notified',False)}
            # Description should stay in repo only if needed? Keep excerpt, not full content.
            record['excerpt']=job.get('description','')[:320]
            record.pop('description',None)
            state['jobs'][jid]=record
            if tier=='match' and not record['notified']:
                new.append(record)
        if src['kind'] not in ('jobicy','remotive','arbeitnow','rss_signal'):
            for jid, old in state['jobs'].items():
                if old.get('source_id')==sid and jid not in seen:old['active']=False
    state['last_run']=now
    # Collapse across different advertising sources before delivering alerts.
    existing_notified={group_key(j) for j in state['jobs'].values() if j.get('notified')}
    new_groups=grouped_jobs([j for j in state['jobs'].values() if j.get('active') and j.get('tier')=='match'])
    return state,[g for g in new_groups if group_key(g) not in existing_notified]


def send_telegram(jobs, session=None):
    """Only mark jobs notified when every Telegram request succeeds."""
    token=os.environ.get('TELEGRAM_BOT_TOKEN','').strip()
    chat=os.environ.get('TELEGRAM_CHAT_ID','').strip()
    if not (token and chat):
        LOG.warning('Telegram not configured; preserving unnotified jobs for later run')
        return False
    if not jobs:return True
    chunks=[]
    for j in sorted(jobs,key=lambda x:x['score'],reverse=True):
        line=(f'• <b>{html.escape(j["title"])}</b> — {html.escape(j["company"])}\n'
              f'  {html.escape(j["location"] or "Location needs verification")} · Score {j["score"]}\n'
              f'  <a href="{html.escape(j["url"],quote=True)}">View job</a>')
        if len(line)>3000:line=line[:3000]
        if not chunks or len(chunks[-1])+len(line)>3500:
            chunks.append('🎬 <b>New Houdini / animation matches</b>\n\n'+line)
        else:chunks[-1]+='\n\n'+line
    sess=session or requests
    try:
        for chunk in chunks:
            resp=sess.post(f'https://api.telegram.org/bot{token}/sendMessage',json={
                'chat_id':chat,'text':chunk,'parse_mode':'HTML','disable_web_page_preview':True},timeout=TIMEOUT)
            resp.raise_for_status()
            if not resp.json().get('ok',False):raise ValueError('Telegram API returned ok=false')
        return True
    except (requests.RequestException,ValueError) as exc:
        LOG.error('Telegram notification failed: %s',exc)
        return False


def send_signal_telegram(signals, session=None):
    """Sends separately labeled *possible* opportunities; never implies a live job."""
    token=os.environ.get('TELEGRAM_BOT_TOKEN','').strip()
    chat=os.environ.get('TELEGRAM_CHAT_ID','').strip()
    if not (token and chat):return False
    if not signals:return True
    sess=session or requests
    for sig in signals[:8]:
        message=('📡 <b>Early animation hiring signal — not a confirmed job</b>\n\n'
                 +html.escape(sig['title'])+'\n'
                 +'<a href="'+html.escape(sig['url'],quote=True)+'">Read public evidence</a>\n'
                 +'If you know someone there, consider asking about upcoming FX needs.')
        try:
            resp=sess.post(f'https://api.telegram.org/bot{token}/sendMessage',json={
                'chat_id':chat,'text':message,'parse_mode':'HTML','disable_web_page_preview':True},timeout=TIMEOUT)
            resp.raise_for_status()
            if not resp.json().get('ok'):return False
        except (requests.RequestException,ValueError):return False
    return True


def atomic_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2,sort_keys=False)+'\n',encoding='utf-8')
    temp.replace(path)


def refresh_jobicy_status(state, session=None):
    """Old Jobicy ads vanish after seven days; absence is not proof of closure.
    Check their documented public batch status API instead.
    """
    candidates=[j for j in state['jobs'].values()
                if j.get('source_id','').startswith('jobicy-') and j.get('active') and j.get('external_id')]
    sess=session or requests
    for start in range(0,len(candidates),100):
        batch=candidates[start:start+100]
        ids=','.join(j['external_id'] for j in batch)
        try:
            data=http_get('https://jobicy.com/api/jobs/status',sess,params={'ids':ids}).json()
            if data.get('success') is False or not isinstance(data.get('jobs'),list):
                raise ValueError('Invalid job status response')
            closed={str(x.get('id')) for x in data['jobs'] if x.get('status')=='closed'}
            for j in batch:
                if j['external_id'] in closed:j['active']=False
        except (requests.RequestException,ValueError) as exc:
            LOG.warning('Could not verify old Jobicy ads: %s',exc)


def run(sources_path=SOURCES_PATH,state_path=STATE_PATH,site_path=SITE_PATH, fetcher=None, notifier=send_telegram):
    sources=json.loads(Path(sources_path).read_text(encoding='utf-8'))
    state=load_state(state_path)
    state.setdefault('signals', {})
    funcs={'greenhouse':fetch_greenhouse,'lever':fetch_lever,'ashby':fetch_ashby,
           'jazzhr':fetch_jazzhr,'bamboohr':fetch_bamboohr,'eightfold':fetch_eightfold,'workable':fetch_workable,
           'html':fetch_html,'jobicy':fetch_jobicy,'rss_signal':fetch_rss_signals,
           'remotive':fetch_remotive,'arbeitnow':fetch_arbeitnow}
    def do_one(src):
        try:
            jobs=(fetcher or funcs[src['kind']])(src)
            return src,dedupe_jobs(jobs),None
        except Exception as exc:
            LOG.error('%s failed: %s',src['name'],exc)
            return src,[],str(exc)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results=list(pool.map(do_one,sources))
    now=utc_now()
    state, new=merge_state(state,results,now)
    # Don't make network requests during synthetic test runs with a custom fetcher.
    if fetcher is None:refresh_jobicy_status(state)
    new=[j for j in new if j.get('active')]
    if new and notifier(new):
        notified_keys={group_key(g) for g in new}
        for job in state['jobs'].values():
            if job['tier']=='match' and job['active'] and group_key(job) in notified_keys:
                job['notified']=True
    active=grouped_jobs([j for j in state['jobs'].values() if j.get('active')])
    signals=sorted(state['signals'].values(),key=lambda x:x.get('published_at') or x.get('first_seen',''),reverse=True)[:120]
    from datetime import timedelta
    threshold=datetime.now(timezone.utc)-timedelta(days=14)
    new_signals=[]
    for sig in signals:
        if not re.search(r'(?i)\b(hiring|recruitment|staffing|greenlit|greenlight|production begins|production underway|expansion|new series|new feature|new season|renewed|commissioned)\b',sig['title']):continue
        try:ts=datetime.fromisoformat(sig['published_at']) if sig.get('published_at') else threshold
        except ValueError:continue
        if ts>=threshold and not sig.get('notified'):new_signals.append(sig)
    if fetcher is None and new_signals and send_signal_telegram(new_signals):
        for sig in new_signals:state['signals'][sig['id']]['notified']=True
    public={'version':2,'last_run':now,'summary':{
        'matches':sum(j.get('tier')=='match' for j in active),
        'review':sum(j.get('tier')=='review' for j in active),
        'signals':len(signals),
        'sources_ok':sum(r[2] is None for r in results),
        'sources_total':len(results)},
        'sources':list(state['sources'].values()),'signals':signals,
        'jobs':sorted(active,key=lambda x:(x.get('tier')=='match',x.get('score',0),x.get('last_seen','')),reverse=True)}
    atomic_json(state_path,state)
    atomic_json(site_path,public)
    LOG.info('Sources %s/%s OK, %s matches, %s review, %s new; Telegram %s',
             public['summary']['sources_ok'],len(results),public['summary']['matches'],
             public['summary']['review'],len(new),'configured' if os.environ.get('TELEGRAM_BOT_TOKEN') else 'not configured')
    return public


def main():
    logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
    parser=argparse.ArgumentParser(description='Personal animated-production Houdini job watcher')
    parser.add_argument('--sources',default=str(SOURCES_PATH))
    parser.add_argument('--state',default=str(STATE_PATH))
    parser.add_argument('--output',default=str(SITE_PATH))
    args=parser.parse_args()
    run(args.sources,args.state,args.output)

if __name__=='__main__':
    main()
