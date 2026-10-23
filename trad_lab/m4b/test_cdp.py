"""Regressions for preparation order, stale contexts and physical budget gates."""
from pathlib import Path
import tempfile
import unittest

from .cdp import install, ensure_document, prepared, approve, reserve_attempt


def ready():
    return {'path':'/operator','complete':True,'operator':True,'panel':True,'gate':{'failed':False,'owner_barrier':True},
        'state':{'page':'one','dom_ready':True,'ready_acknowledged':True,'failed':False,
        'observers':dict.fromkeys(['media','worklet','worker','websocket','dom','controls'],True)}}


class PreparationTests(unittest.TestCase):
    def test_existing_capture_document_installs_but_blank_and_installed_are_untouched(self):
        for state,expected in [({'eligible':False,'installed':False},False),
                               ({'eligible':True,'installed':True},False),
                               ({'eligible':True,'installed':False},True)]:
            calls=[]
            def call(method,params=None,sid=None):
                calls.append((method,params,sid))
                return {'result':{'value':state}} if len(calls)==1 else {}
            self.assertEqual(ensure_document(call,'popup','observer-source'),expected)
            self.assertEqual(len(calls),2 if expected else 1)
            if expected:
                self.assertIn('__m4bGate',calls[1][1]['expression'])
                self.assertIn('observer-source',calls[1][1]['expression'])

    def test_effective_document_script_exception_aborts(self):
        calls=[]
        def call(*args):
            calls.append(args)
            if len(calls)==1:return {'result':{'value':{'eligible':True,'installed':False}}}
            return {'exceptionDetails':{}}
        # CDP provides a nonempty exception object on error.
        def failure(*args):
            result=call(*args)
            if 'exceptionDetails' in result:result['exceptionDetails']={'lineNumber':1}
            return result
        with self.assertRaisesRegex(RuntimeError,'effective-document'):ensure_document(failure,'popup','source')

    def test_paused_popup_is_resumed_before_awaiting_page_enable(self):
        sent=[];waited=[]
        def fire(method,params=None,sid=None):sent.append(method);return len(sent)
        def wait(identifier,method):
            self.assertIn('Runtime.runIfWaitingForDebugger',sent)
            waited.append(method)
        install(None,'popup','source',fire=fire,wait=wait)
        self.assertEqual(sent[0],'Page.enable');self.assertEqual(sent[-1],'Runtime.runIfWaitingForDebugger')
        self.assertEqual(waited,sent)
    def test_page_domain_enabled_before_new_document_registration(self):
        calls=[]
        def call(method,params=None,sid=None):calls.append((method,params,sid));return {}
        install(call,'s','observer-source')
        methods=[c[0] for c in calls]
        self.assertLess(methods.index('Page.enable'),methods.index('Page.addScriptToEvaluateOnNewDocument'))
        sources=[c[1]['source'] for c in calls if c[0]=='Page.addScriptToEvaluateOnNewDocument']
        self.assertIn('__m4bGate',sources[0]);self.assertIn('observer-source',sources[1])

    def test_missing_ack_panel_or_observer_never_prepared(self):
        self.assertTrue(prepared(ready()))
        for kind in ['ack','panel','observer','failure','gate','owner-barrier']:
            v=ready()
            if kind=='ack':v['state']['ready_acknowledged']=False
            elif kind=='panel':v['panel']=False
            elif kind=='observer':v['state']['observers']['media']=False
            elif kind=='failure':v['state']['failed']=True
            elif kind=='owner-barrier':v['gate']['owner_barrier']=False
            else:v['gate']['failed']=True
            self.assertFalse(prepared(v),kind)

    def test_failure_consumes_no_budget_and_existing_attempt_is_preserved(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]/'logs') as folder:
            plan=Path(folder)/'plan.json';old=Path(folder)/'physical_attempt_01.claim';old.write_text('prior failed attempt')
            with self.assertRaisesRegex(RuntimeError,'no physical attempt'):reserve_attempt(plan,'out',{})
            self.assertEqual(len(list(Path(folder).glob('*.claim'))),1)
            with self.assertRaisesRegex(RuntimeError,'both documents'):reserve_attempt(plan,'out',ready())
            child=ready();child['path']='/capture'
            child['state']['ready_acknowledged']=False
            with self.assertRaisesRegex(RuntimeError,'both documents'):reserve_attempt(plan,'out',ready(),child)
            child['state']['ready_acknowledged']=True
            self.assertEqual(reserve_attempt(plan,'new',ready(),child),2)
            self.assertEqual(old.read_text(),'prior failed attempt')

    def test_two_prior_claims_preserved_and_budget_never_restarts(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]/'logs') as folder:
            plan=Path(folder)/'plan.json'
            for number in (1,2):(Path(folder)/f'physical_attempt_{number:02d}.claim').write_text(f'original-{number}')
            child=ready();child['path']='/capture'
            self.assertEqual(reserve_attempt(plan,'new',ready(),child),3)
            with self.assertRaisesRegex(RuntimeError,'budget exhausted'):reserve_attempt(plan,'new',ready(),child)
            for number in (1,2):self.assertEqual((Path(folder)/f'physical_attempt_{number:02d}.claim').read_text(),f'original-{number}')

    def test_browser_rejection_or_stale_context_cannot_enable_start(self):
        calls=[]
        def call(*args,**kw):calls.append(args);return {'result':{'value':False}}
        with self.assertRaisesRegex(RuntimeError,'stale'):approve(call,'session',ready())
        self.assertEqual(len(calls),1)
        with self.assertRaisesRegex(RuntimeError,'missing'):approve(call,'session',{})
        self.assertEqual(len(calls),1)


if __name__=='__main__':unittest.main()
