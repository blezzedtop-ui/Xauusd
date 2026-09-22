"""Offline regression tests. Synthetic OHLC fixtures are NOT a performance backtest."""
import asyncio
import copy
import json
import math
import os
import random
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

# Never import the app against an owner's production database or credentials.
_test_dir = tempfile.TemporaryDirectory(prefix="signalx-suite-tests-")
os.environ.update(ADMIN_LOGIN="test-admin",ADMIN_PASSWORD="test-only-password-123",
                  SECRET_KEY="test-only-secret",DATABASE_URL="sqlite:///"+_test_dir.name+"/suite.db",
                  MT5_AUTO_TRADING="false",MT5_EXECUTION_TRANSPORT="legacy")

import main as core
import strategy_service as service
import strategy_suite as suite
import mt5_account_gateway as gateway
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

NOW = 1800000030.0
SEEDS = {"trend":3,"fibonacci":5,"ai-analysis":14,"snr":22,"technical":24,
         "trendline":75,"ob":352,"classic":1010,"ict-ai-pro":2884}


def candles(seed=3, seconds=300, mirror=False):
    r=random.Random(seed); price=100; out=[]
    for i in range(120):
        o=price; price+=r.gauss(.01,.45)
        out.append(dict(time=int(NOW//seconds)*seconds-(120-i)*seconds,open=o,close=price,
                        high=max(o,price)+r.uniform(.01,.3),low=min(o,price)-r.uniform(.01,.3)))
    return reflect(out) if mirror else out


def higher(seconds=1800,mirror=False):
    out=[dict(time=int(NOW//seconds)*seconds-(120-i)*seconds,open=100+i*.15,
              high=100.3+i*.15,low=99.8+i*.15,close=100.2+i*.15) for i in range(120)]
    return reflect(out) if mirror else out


def reflect(cs):
    return [dict(time=c["time"],open=300-c["open"],close=300-c["close"],high=300-c["low"],low=300-c["high"]) for c in cs]


def ai(direction="BUY"):
    return dict(mode="groq",signal=direction,validation=True,confidence=90,agreement=90,risk_flags=[],reasoning="Offline test fixture")


def pipeline_candidate(mid,cs,hs,rr):
    # Pipeline tests isolate transport/storage from engine tests above/below.
    return dict(module_id=mid,source=suite.MODULES[mid]["source"],strategy=suite.MODULES[mid]["name"],
                contract_version=suite.VERSION,signal="BUY",entry=100.0,stop_loss=99.0,take_profit=[100+rr],
                risk_reward=rr,atr=2,confidence=85,evidence={"fixture":True},reason="offline fixture",state="AWAITING_AI")


class EngineTests(unittest.TestCase):
    def test_all_nine_have_real_buy_and_sell_paths(self):
        for mid,seed in SEEDS.items():
            for mirrored in [False,True]:
                with self.subTest(module=mid,mirror=mirrored):
                    cs=candles(seed,mirror=mirrored); hs=higher(mirror=mirrored)
                    before=copy.deepcopy((cs,hs))
                    result=suite.analyze(mid,cs,hs,1.0)
                    self.assertEqual(result["signal"],"SELL" if mirrored else "BUY")
                    self.assertGreaterEqual(result["risk_reward"],1-1e-8)
                    self.assertEqual((cs,hs),before)
                    self.assertEqual(result["source"],suite.MODULES[mid]["source"])
                    self.assertEqual(suite.analyze(mid,cs,hs,1.0),result)

    def test_rr_boundaries_and_invalid_geometry(self):
        for rr in [1,1.0001,1.2,1.4,1.5,2,3.75,10,10000]:
            self.assertAlmostEqual(suite.reward_risk("BUY",100,99,[100+rr]),rr)
            self.assertAlmostEqual(suite.reward_risk("SELL",20000,20001,[20000-rr]),rr)
        for direction,e,s,tps in [("BUY",100,101,[102]),("SELL",100,99,[98]),("BUY",100,100,[102]),
                                  ("BUY",100,99,[98]),("BUY",100,99,[]),("BUY",100,99,[102,101]),
                                  ("BUY",math.nan,99,[102]),("BUY",100,99,[math.inf]),("WAIT",100,99,[102])]:
            self.assertIsNone(suite.reward_risk(direction,e,s,tps))
        for rr in [0,.99,-1,math.nan,math.inf]:
            with self.assertRaises(ValueError): suite.analyze("trend",candles(),higher(),rr)

    def test_closed_candle_excludes_forming_and_validates_data(self):
        cs=candles(); seconds=300
        forming=dict(time=int(NOW//seconds)*seconds,open=100,low=1,high=999,close=500)
        self.assertEqual(suite.closed_candles(cs+[forming],seconds,NOW),cs)
        invalids=[]
        bad=copy.deepcopy(cs);bad[-1]["high"]=0;invalids.append(bad)
        bad=copy.deepcopy(cs);bad[-1]["close"]=math.nan;invalids.append(bad)
        bad=copy.deepcopy(cs);bad[-1]["time"]=NOW+300;invalids.append(bad)
        invalids.extend([cs[::-1],cs[:-1]+[cs[-2]],cs[:-6],cs[:50],cs[:-4]+cs[-3:]])
        for bad in invalids:
            with self.assertRaises(ValueError):suite.closed_candles(bad,seconds,NOW)

    def test_missing_structure_does_not_force_signal(self):
        flat=[dict(time=i*300,open=100,high=100.1,low=99.9,close=100) for i in range(120)]
        for mid in suite.MODULES:
            x=suite.analyze(mid,flat,flat,1)
            self.assertEqual(x["signal"],"WAIT")
            self.assertIsNone(x["entry"])

    def test_rr_configuration_cannot_force_target_through_obstacle(self):
        x=suite.analyze("fibonacci",candles(SEEDS["fibonacci"]),higher(),1000)
        self.assertEqual(x["signal"],"WAIT")
        self.assertEqual(x["state"],"TARGET_BLOCKED_BY_STRUCTURE")


class PipelineTests(unittest.TestCase):
    def setUp(self):
        with core.SessionLocal() as db:
            for model in [gateway.MTOrder,gateway.MTSymbol,gateway.MT5Account,service.StrategyOutbox,
                          service.StrategyEvent,service.StrategyConfig,core.SignalHistory]:
                db.execute(delete(model))
            db.commit()
            self.admin=db.scalar(select(core.User).where(core.User.role=="admin"))
            self.admin_id=self.admin.id
        core.MT5_ORDER_QUEUE.clear();core.MT5_EXECUTED_KEYS.clear()
        core.MT5_AUTO_TRADING=True;core.AUTO_ENTRY_ENABLED=True
        service.TRANSPORT="legacy"
        service.LOCKS={m:asyncio.Lock() for m in suite.MODULES};service.AI_SLOTS=asyncio.Semaphore(3)
        self.auth="Bearer "+core.AUTOTRADE_INTERNAL_TOKEN
        self.stack=[]
        async def data(symbol,tf,limit):
            cs=candles(seconds=core.TIMEFRAME_SECONDS[tf])
            # Current feed price equals fixture Entry so RR=1 can pass.
            last=dict(time=int(NOW//core.TIMEFRAME_SECONDS[tf])*core.TIMEFRAME_SECONDS[tf],open=100,high=100.1,low=99.9,close=100)
            return dict(mode="live",provider="tradingview",candles=cs+[last])
        for p in [patch.object(service,"_now",return_value=NOW),patch.object(core,"market_gate_status",return_value={"open":True}),
                  patch.object(core,"get_market_snapshot",side_effect=data),patch.object(suite,"analyze",side_effect=pipeline_candidate),
                  patch.object(service,"validate_ai",new=AsyncMock(return_value=ai()))]:
            self.stack.append(p);p.start()

    def tearDown(self):
        for p in reversed(self.stack):p.stop()
        core.MT5_AUTO_TRADING=False

    def run_async(self,coro):return asyncio.run(coro)

    def test_scanner_writes_every_module_and_queues_without_browser(self):
        with core.SessionLocal() as db:
            admin=db.get(core.User,self.admin_id)
            for mid in suite.MODULES:
                db.add(service.StrategyConfig(module_id=mid,interval=suite.MODULES[mid]["interval"],target_rr=1))
            db.commit()
            result=self.run_async(service.scan(db,admin))
            self.assertEqual(result["queued"],9)
            rows=list(db.scalars(select(core.SignalHistory).where(core.SignalHistory.user_id==admin.id)))
            self.assertEqual(len(rows),9)
            self.assertEqual({r.source for r in rows},suite.SOURCES)
            self.assertEqual(len({r.signal_uid for r in rows}),9)
            self.assertTrue(all(abs(r.risk_reward-1)<1e-8 for r in rows))
            second=self.run_async(service.scan(db,admin))
            self.assertEqual(second["count"],0);self.assertEqual(second["queued"],0)
            self.assertEqual(len(core.MT5_ORDER_QUEUE),9)

    def test_repeated_concurrent_requests_validate_once(self):
        async def run():return await asyncio.gather(*(service.evaluate("trend") for _ in range(8)))
        out=self.run_async(run())
        self.assertEqual(service.validate_ai.await_count,1)
        self.assertEqual(len({x["event_id"] for x in out}),1)

    def test_rr_edit_does_not_repaint_existing_event(self):
        first=self.run_async(service.evaluate("trend"))
        with core.SessionLocal() as db:
            self.run_async(service.configure("trend",service.ConfigBody(interval="15min",target_rr=1),self.auth,db))
        second=self.run_async(service.evaluate("trend"))
        self.assertEqual(first["take_profit"],second["take_profit"])
        with patch.object(service,"_now",return_value=NOW+900):
            third=self.run_async(service.evaluate("trend"))
        # The previous forming bar is now closed; the new RR applies once.
        self.assertNotEqual(first["event_id"],third["event_id"])
        self.assertEqual(third["take_profit"],[101])
        with patch.object(service,"_now",return_value=NOW+2700):
            stale=self.run_async(service.evaluate("trend"))
        self.assertEqual(stale["signal"],"WAIT")

    def test_failed_ai_is_cached_and_cannot_reach_history_or_queue(self):
        for bad in [ai()|{"validation":False},ai()|{"mode":"fallback"},ai()|{"signal":"SELL"},
                    ai()|{"confidence":84},ai()|{"agreement":69},ai()|{"validation":"true"},
                    ai()|{"risk_flags":["CONFLICT"]},ai()|{"confidence":math.nan}]:
            with self.subTest(bad=bad):
                with core.SessionLocal() as db:db.execute(delete(service.StrategyEvent));db.commit()
                service.validate_ai.return_value=bad
                x=self.run_async(service.evaluate("snr"))
                self.assertEqual(x["signal"],"WAIT")
                with core.SessionLocal() as db:self.assertEqual(service.persist(db,self.admin_id,x),(None,False))
                self.assertEqual(len(core.MT5_ORDER_QUEUE),0)

    def test_stale_wrong_provider_and_market_closed_fail_closed(self):
        for snap in [dict(mode="live",provider="yahoo",candles=candles()),dict(mode="demo",provider="tradingview",candles=candles()),
                     dict(mode="live",provider="tradingview",candles=candles()[:-8])]:
            with patch.object(core,"get_market_snapshot",new=AsyncMock(return_value=snap)):
                self.assertEqual(self.run_async(service.evaluate("snr"))["signal"],"WAIT")
        self.assertEqual(service.validate_ai.await_count,0)
        with patch.object(core,"market_gate_status",return_value={"open":False}):
            self.assertEqual(self.run_async(service.evaluate("snr"))["state"],"MARKET_CLOSED")

    def test_client_cannot_forge_levels_source_or_rr(self):
        client=TestClient(core.app)
        bad=client.post('/api/v1/signals/record-module',headers={"Authorization":self.auth},json={
            "source":"ICT Signals","direction":"BUY","entry":100,"stop_loss":99,"take_profit":[1000]})
        self.assertFalse(bad.json()["saved"])
        reply=client.post('/api/v1/signals/record-module',headers={"Authorization":self.auth},json={
            "source":"SNR","direction":"SELL","entry":1,"stop_loss":2,"take_profit":[.5],"payload":{"ai_validation":ai()}})
        self.assertEqual(reply.status_code,200)
        with core.SessionLocal() as db:
            row=db.scalar(select(core.SignalHistory).where(core.SignalHistory.signal_uid==reply.json()["signal_id"]))
            self.assertEqual(row.direction,"BUY");self.assertEqual(row.entry_price,100)
            self.assertEqual(row.take_profit_1,102)
        self.assertEqual(client.get('/api/v1/strategies').status_code,401)
        self.assertEqual(client.get('/api/v1/ict-ai-pro/XAU%2FUSD').status_code,404)

    def test_config_allows_arbitrary_rr_ge_one_only_for_admin(self):
        client=TestClient(core.app);headers={"Authorization":self.auth}
        for rr in [1,1.05,1.4,2.7,10000]:
            self.assertEqual(client.put('/api/v1/strategies/snr/config',headers=headers,json={"interval":"5min","target_rr":rr}).status_code,200)
        for rr in [.99,0,-1,"Infinity","NaN"]:
            self.assertEqual(client.put('/api/v1/strategies/snr/config',headers=headers,json={"interval":"5min","target_rr":rr}).status_code,422)

    def test_queue_rejects_metadata_rr_bypass_and_replays(self):
        x=self.run_async(service.evaluate("snr"))
        with core.SessionLocal() as db:
            row,_=service.persist(db,self.admin_id,x)
            args=dict(symbol="XAU/USD",source="SNR",interval=x["interval"],direction="BUY",entry=100,sl=99,tp=[100.5],
                      volume=.01,confidence=90,candle_time=x["candle_time"],risk_reward=999,signal_id=row.signal_uid)
            self.assertIsNone(core._queue_autotrade_order(**args))
            args["tp"]=[math.nan];self.assertIsNone(core._queue_autotrade_order(**args))
            args["tp"]=[102];args["source"]="ICT Signals";self.assertIsNone(core._queue_autotrade_order(**args))
            order=self.run_async(service.dispatch(db,row,x));self.assertIsNotNone(order)
            core.MT5_ORDER_QUEUE.clear();service.restore_outbox()
            self.assertEqual(core.MT5_ORDER_QUEUE[0]["id"],order["id"])
            self.assertTrue(service.claim_legacy(row.signal_uid))
            self.assertFalse(service.claim_legacy(row.signal_uid))
            core.MT5_ORDER_QUEUE.clear();service.restore_outbox();self.assertEqual(core.MT5_ORDER_QUEUE,[])

    def test_autotrade_off_still_records_and_does_not_queue(self):
        core.MT5_AUTO_TRADING=False
        with core.SessionLocal() as db:
            result=self.run_async(service.scan(db,db.get(core.User,self.admin_id)))
            self.assertGreaterEqual(result["count"],9);self.assertEqual(result["queued"],0)

    def test_gateway_carries_module_and_owner_ids_without_duplicates(self):
        service.TRANSPORT="gateway"
        with core.SessionLocal() as db:
            viewer=db.scalar(select(core.User).where(core.User.username=="test-viewer"))
            if not viewer:
                viewer=core.User(username="test-viewer",email="viewer@example.test",role="user",password_hash="not-a-real-password")
                db.add(viewer);db.commit()
            for uid in [self.admin_id,viewer.id]:
                account=gateway.MT5Account(user_id=uid,auto_trade_enabled=True,trade_allowed=True)
                db.add(account);db.flush()
                db.add(gateway.MTSymbol(account_id=account.id,canonical_symbol="XAU/USD",broker_symbol="XAUUSDm"))
            db.commit()
            self.run_async(service.scan(db,db.get(core.User,self.admin_id)))
            orders=list(db.scalars(select(gateway.MTOrder)))
            self.assertEqual(len(orders),18)
            self.assertEqual({o.source for o in orders},suite.SOURCES)
            for order in orders:
                account=db.get(gateway.MT5Account,order.account_id)
                h=db.scalar(select(core.SignalHistory).where(core.SignalHistory.signal_uid==order.signal_id))
                self.assertEqual(h.user_id,account.user_id)
            gateway._sync_core_queue(db)
            self.assertEqual(len(list(db.scalars(select(gateway.MTOrder)))),18)
            account=db.scalar(select(gateway.MT5Account).where(gateway.MT5Account.user_id==self.admin_id))
            with patch.object(gateway,"_auth_account",return_value=account):
                delivered=self.run_async(gateway.poll("test",db))
                self.assertEqual(len(delivered["orders"]),1)
                item=delivered["orders"][0]
                self.run_async(gateway.report(gateway.ReportRequest(order_id=item["order_id"],status="FILLED",broker_ticket="test-ticket"),"test",db))
                h=db.scalar(select(core.SignalHistory).where(core.SignalHistory.signal_uid==item["signal_id"]))
                self.assertEqual(json.loads(h.payload)["executions_by_account"][str(account.id)]["status"],"FILLED")
                again=self.run_async(gateway.poll("test",db))
                self.assertNotEqual(again["orders"][0]["order_id"],item["order_id"])

    def test_history_filters_stats_keep_nine_sources_separate(self):
        with core.SessionLocal() as db:self.run_async(service.scan(db,db.get(core.User,self.admin_id)))
        client=TestClient(core.app);headers={"Authorization":self.auth}
        with patch.object(core,"_maybe_refresh_history_v2",new=AsyncMock()):
            for source in suite.SOURCES:
                reply=client.get('/api/v2/signal-history',headers=headers,params={"module":source})
                self.assertEqual(reply.status_code,200)
                self.assertEqual(reply.json()["total_count"],1)
                self.assertEqual(reply.json()["items"][0]["source"],source)
            stats=client.get('/api/v2/signal-history/stats',headers=headers)
            self.assertEqual(stats.status_code,200)
            self.assertEqual(set(stats.json()["by_module"]),suite.SOURCES)

    def test_live_price_drift_cannot_bypass_rr_at_dispatch(self):
        x=self.run_async(service.evaluate("snr"))
        with core.SessionLocal() as db:
            row,_=service.persist(db,self.admin_id,x)
            cs=candles();cs[-1]=dict(cs[-1],open=101.5,high=102,low=101,close=101.5)
            with patch.object(core,"get_market_snapshot",new=AsyncMock(return_value=dict(mode="live",provider="tradingview",candles=cs))):
                self.assertIsNone(self.run_async(service.dispatch(db,row,x)))
            self.assertEqual(core.MT5_ORDER_QUEUE,[])

    def test_stale_client_and_cross_timeframe_order_are_rejected(self):
        with core.SessionLocal() as db:
            response=self.run_async(service.record("snr",self.auth,db,event_id="wrong-event"))
            self.assertEqual(response["reason"],"STALE_CLIENT_EVENT")
            x=self.run_async(service.evaluate("snr"));row,_=service.persist(db,self.admin_id,x)
            self.assertFalse(service.authorized_order("SNR","BUY",100,99,[102],row.signal_uid,"4h",x["candle_time"]))
            self.assertFalse(service.authorized_order("SNR","BUY",100,99,[102],row.signal_uid,x["interval"],"wrong-candle"))

    def test_old_history_is_preserved_but_cannot_inflate_new_statistics(self):
        with core.SessionLocal() as db:
            db.add(core.SignalHistory(user_id=self.admin_id,symbol="XAU/USD",interval="5min",source="SNR",direction="BUY",
                headline="Old algorithm",price=100,payload='{}',candle_time="old-candle",outcome="TP HIT"))
            db.commit();core._prepare_live_history_once()
            self.assertEqual(len(list(db.scalars(select(core.SignalHistory)))),1)
        with patch.object(core,"_maybe_refresh_history_v2",new=AsyncMock()):
            reply=TestClient(core.app).get('/api/v2/signal-history',headers={"Authorization":self.auth})
            self.assertEqual(reply.json()["total_count"],0)

    def test_history_never_scores_price_action_before_signal_creation(self):
        from datetime import datetime,timezone
        x=self.run_async(service.evaluate("snr"))
        with core.SessionLocal() as db:
            row,_=service.persist(db,self.admin_id,x)
            row.created_at=datetime.fromtimestamp(NOW+120,timezone.utc);db.commit()
            cs=candles();cs.append(dict(time=int(NOW//300)*300,open=100,high=103,low=98,close=100))
            with patch.object(core,"get_strict_live_candles",new=AsyncMock(return_value=(cs,"tradingview","TradingView",None,None))):
                self.run_async(core.refresh_signal_outcomes(db,self.admin_id))
            db.refresh(row)
            self.assertEqual(row.status,"ACTIVE")


if __name__ == '__main__': unittest.main()
