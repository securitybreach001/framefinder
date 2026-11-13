import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from jobwatch.core import (analyze, make_job, merge_state, fetch_greenhouse,
                           fetch_bamboohr, fetch_jazzhr, fetch_jobicy, run, html_candidates, salary_hint)
from bs4 import BeautifulSoup

ANIM = {'id':'stellar','name':'Stellar Creative Lab','studio':'animation','kind':'jazzhr'}
MIXED = {'id':'sony','name':'Sony Pictures Imageworks','studio':'mixed','kind':'greenhouse'}
OTHER = {'id':'remote','name':'Remote job board','studio':'other','kind':'jobicy'}


def job(src=ANIM,title='Senior 3D FX Artist',location='Vancouver, BC',desc='Create destruction in Houdini.',remote=False):
    return make_job(src,title,'https://example.com/job/123',location,desc,remote=remote)

class Filtering(unittest.TestCase):
    def test_animation_vancouver(self):
        self.assertEqual(analyze(job())[0],'match')
    def test_studio_mixed_unconfirmed_is_not_notified(self):
        self.assertEqual(analyze(job(src=MIXED))[0],'review')
    def test_studio_mixed_explicit_animation(self):
        self.assertEqual(analyze(job(src=MIXED,desc='Working in our fully animated feature production using Houdini'))[0],'match')
    def test_live_action_excluded_everywhere(self):
        self.assertEqual(analyze(job(desc='FX for a live-action film.'))[0],'excluded')
    def test_montreal_onsite_is_not_eligible(self):
        self.assertEqual(analyze(job(location='Montréal, QC, Canada'))[0],'review')
    def test_montreal_remote_is_eligible(self):
        self.assertEqual(analyze(job(location='Remote — Montréal, Canada',remote=True))[0],'match')
    def test_us_only_remote_is_ineligible(self):
        self.assertEqual(analyze(job(src=OTHER,location='Remote, United States',remote=True))[0],'excluded')
    def test_us_remote_accepts_work_from_canada(self):
        self.assertEqual(analyze(job(src=OTHER,location='Remote, United States',remote=True,desc='This remote role is open to applicants working from Canada.'))[0],'match')
    def test_unknown_remote_location_review(self):
        self.assertEqual(analyze(job(src=OTHER,location='Remote',remote=True))[0],'review')
    def test_jewelry_related(self):
        self.assertEqual(analyze(job(src=OTHER,title='Procedural Jewelry Designer',location='Anywhere / Remote',remote=True))[0],'match')
    def test_unrelated_role_filtered(self):
        self.assertEqual(analyze(job(title='3D Marketing Manager'))[0],'excluded')
    def test_expression_of_interest_is_review(self):
        self.assertEqual(analyze(job(title='FX Artist - Expression of Interest'))[0],'review')

class Storage(unittest.TestCase):
    def test_no_repeat_notifications(self):
        s={'version':1,'sources':{},'jobs':{}}
        j=job()
        s, new=merge_state(s,[(ANIM,[j],None)],'2026-11-12T18:00:00+00:00')
        self.assertEqual(len(new),1)
        s['jobs'][j['id']]['notified']=True
        s,new=merge_state(s,[(ANIM,[j],None)],'2026-11-13T18:00:00+00:00')
        self.assertEqual(new,[])
        self.assertTrue(s['jobs'][j['id']]['active'])
    def test_failed_source_keeps_previous_jobs_active(self):
        s={'version':1,'sources':{},'jobs':{}}
        j=job()
        s,_=merge_state(s,[(ANIM,[j],None)],'2026-11-12T18:00:00+00:00')
        s,_=merge_state(s,[(ANIM,[],"blocked")],'2026-11-13T18:00:00+00:00')
        self.assertTrue(s['jobs'][j['id']]['active'])
        self.assertEqual(s['sources']['stellar']['status'],'error')
    def test_confirmed_empty_marks_inactive(self):
        s={'version':1,'sources':{},'jobs':{}}
        j=job()
        s,_=merge_state(s,[(ANIM,[j],None)],'2026-11-12T18:00:00+00:00')
        s,_=merge_state(s,[(ANIM,[],None)],'2026-11-13T18:00:00+00:00')
        self.assertFalse(s['jobs'][j['id']]['active'])
    def test_end_to_end_with_fake_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)
            sp=path/'sources.json'; sp.write_text(json.dumps([ANIM]),encoding='utf-8')
            outputs=[]
            def notifier(jobs): outputs.extend(jobs);return True
            a=run(sp,path/'state.json',path/'site.json',fetcher=lambda _: [job()],notifier=notifier)
            b=run(sp,path/'state.json',path/'site.json',fetcher=lambda _: [job()],notifier=notifier)
            self.assertEqual(len(outputs),1)
            self.assertEqual(a['summary']['matches'],1)
            self.assertEqual(b['summary']['matches'],1)
            self.assertTrue(json.loads((path/'site.json').read_text())['jobs'][0]['notified'])

class Parsers(unittest.TestCase):
    def test_greenhouse_api(self):
        sess=Mock()
        sess.get.return_value.json.return_value={'jobs':[{'id':17,'internal_job_id':19,'title':'FX Artist','absolute_url':'https://job-boards.greenhouse.io/atomic/jobs/17','location':{'name':'Vancouver'},'content':'Houdini FX in animation'}]}
        src={**ANIM,'kind':'greenhouse','board':'atomiccartoons'}
        out=fetch_greenhouse(src,sess)
        self.assertEqual(out[0]['title'],'FX Artist')
        self.assertEqual(out[0]['location'],'Vancouver')
    def test_jazzhr_page(self):
        src={**ANIM,'url':'https://stellarcreativelab.applytojob.com/apply'}
        listing=Mock(url=src['url'],text='<html><div><h3><a href="/apply/XFyUutVK60/3D-FX-Artist-mid-Senior">3D FX Artist (mid-senior)</a></h3><p>Vancouver, BC, Canada</p></div></html>')
        detail=Mock(url='https://stellarcreativelab.applytojob.com/apply/XFyUutVK60/3D-FX-Artist-mid-Senior',text='<html><main><h1>3D FX Artist (mid-senior)</h1><p>Vancouver, BC, Canada</p><p>Houdini and animated series</p></main></html>')
        sess=Mock();sess.get.side_effect=[listing,detail]
        out=fetch_jazzhr(src,sess)
        self.assertEqual(len(out),1)
        self.assertEqual(analyze(out[0])[0],'match')
    def test_html_jsonld(self):
        src={**ANIM,'url':'https://studio.example/careers'}
        soup=BeautifulSoup('<script type="application/ld+json">{"@type":"JobPosting","title":"FX Artist","url":"https://studio.example/job/17","jobLocation":{"address":{"addressLocality":"Vancouver","addressRegion":"BC"}}}</script>','html.parser')
        result=html_candidates(soup,src['url'],src)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['location'],'Vancouver, BC')
    def test_jobicy(self):
        sess=Mock()
        sess.get.return_value.json.return_value={'success':True,'jobs':[{'id':10,'jobTitle':'Houdini Simulation Artist','jobGeo':'Canada','companyName':'TestCo','url':'https://jobicy.com/jobs/test','jobDescription':'Remote work from Canada'}]}
        result=fetch_jobicy({**OTHER,'tag':'houdini'},sess)
        self.assertEqual(result[0]['company'],'TestCo')
        self.assertEqual(analyze(result[0])[0],'match')

if __name__=='__main__':unittest.main()

class StatusAPI(unittest.TestCase):
    def test_jobicy_closed_after_feed_expiry(self):
        from jobwatch.core import refresh_jobicy_status
        src={'id':'jobicy-houdini','name':'Jobicy','kind':'jobicy','studio':'other'}
        j=make_job(src,'Houdini FX Artist','https://jobicy.com/jobs/1','Canada','',raw_id=123,remote=True)
        j.update(active=True,tier='match')
        state={'jobs':{j['id']:j}}
        sess=Mock();sess.get.return_value.json.return_value={'success':True,'jobs':[{'id':123,'status':'closed'}]}
        refresh_jobicy_status(state,sess)
        self.assertFalse(state['jobs'][j['id']]['active'])

class GroupedResults(unittest.TestCase):
    def test_two_boards_one_job_with_both_links(self):
        from jobwatch.core import grouped_jobs
        a=job();a.update(tier='match',score=92,active=True,first_seen='2026-11-12T18:00:00+00:00',source_label='Official',source_kind='jazzhr')
        b=job(src={'id':'board','name':'Stellar Creative Lab','studio':'animation','kind':'greenhouse'},location='Vancouver BC')
        b.update(tier='match',score=91,active=True,first_seen='2026-11-13T18:00:00+00:00',source_label='LinkedIn',source_kind='official_import',url='https://example.com/secondary')
        result=grouped_jobs([a,b])
        self.assertEqual(len(result),1)
        self.assertEqual({x['label'] for x in result[0]['sources']},{'Official','LinkedIn'})
        self.assertEqual(result[0]['url'],a['url'])
    def test_same_company_different_titles_not_collapsed(self):
        from jobwatch.core import grouped_jobs
        a=job();b=job(title='Senior Houdini TD')
        for j in (a,b):j.update(tier='match',score=92,active=True,first_seen='2026-11-12T18:00:00+00:00')
        self.assertEqual(len(grouped_jobs([a,b])),2)
    def test_salary_and_remote_badges(self):
        from jobwatch.core import salary_hint,guess_arrangement
        j=job(desc='Hybrid. Salary CAD $105,000 - $130,000 per year')
        self.assertIn('$105,000',salary_hint(j))
        self.assertEqual(guess_arrangement(j),'Hybrid')

class PayAndDiscovery(unittest.TestCase):
    def test_bamboohr_reads_separate_compensation_field(self):
        source={**ANIM,'board':'iconcreative','kind':'bamboohr'}
        session=Mock()
        session.get.return_value.json.side_effect=[
            {'result':[{'id':50,'jobOpeningName':'Intermediate FX Artist'}]},
            {'result':{'jobOpening':{
                'description':'Create effects in Houdini.',
                'compensation':'$74,863.88 - $85,000.00 per year',
                'location':{'city':'Vancouver','province':'BC'},
            }}},
        ]
        jobs=fetch_bamboohr(source,session)
        self.assertEqual(salary_hint(jobs[0]),'$74,863.88 - $85,000.00 per year')

    def test_active_cross_post_keeps_inactive_record_discovery_date(self):
        from unittest.mock import patch
        previous='2026-11-11T18:00:00+00:00'
        now='2026-11-12T18:00:00+00:00'
        second_source={**ANIM,'id':'stellar-second-board'}
        state={'sources':{},'jobs':{}}
        old=job()
        state,_=merge_state(state,[(ANIM,[old],None)],previous)
        state,_=merge_state(state,[(ANIM,[],None)],previous)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            state_path=root/'state.json'
            state_path.write_text(json.dumps(state),encoding='utf-8')
            config_path=root/'sources.json'
            config_path.write_text(json.dumps([second_source]),encoding='utf-8')
            new=make_job(second_source,'FX Lead','https://example.com/job/124','Vancouver, BC')
            with patch('jobwatch.core.utc_now',return_value=now):
                public=run(config_path,state_path,root/'site.json',
                           fetcher=lambda source: [job(src=source),new],
                           notifier=lambda jobs: False)
        dates={j['title']:j['first_seen'] for j in public['jobs']}
        self.assertEqual(dates,{'Senior 3D FX Artist':previous,'FX Lead':now})
