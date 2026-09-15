#property strict
#property version   "1.6"
#property description "SignalX dual-symbol XAUUSD + EURUSD MT5 bridge"

#include <Trade/Trade.mqh>
CTrade trade;

input string ApiBase="https://signalx.asia";
input string BridgeToken="e9ea78449cf5bb28414875b57d61e489a5e766a4836be013b332c6a4e509dc21";
input int    PollSeconds=2;
input int    StateSeconds=5;
input double DefaultLot=0.01;
input string XAUTradeSymbol="XAUUSDm";
input string EURTradeSymbol="EURUSDm";
input long   SignalXMagic=26091401;
input int    DuplicateCooldownSeconds=30;
input string BridgeClientId=""; // blank = account-specific client id
input bool   SingleSession=true; // only one EA instance per MT5 terminal/account
input int    SessionLeaseSeconds=15;

string Url(string path){ return ApiBase+path; }
datetime g_last_state=0;
bool g_session_owner=false;
string SessionKey()
{
   return "SignalX.session."+IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN));
}

bool AcquireSession()
{
   if(!SingleSession) return true;
   string key=SessionKey();
   datetime now=TimeCurrent();
   if(GlobalVariableCheck(key))
   {
      double stamp=GlobalVariableGet(key);
      if((now-(datetime)stamp) < SessionLeaseSeconds)
      {
         Print("[MT5 BRIDGE] DUPLICATE INSTANCE BLOCKED key=",key);
         return false;
      }
   }
   if(!GlobalVariableSet(key,(double)now))
   {
      Print("[MT5 BRIDGE] SESSION LOCK FAILED key=",key);
      return false;
   }
   g_session_owner=true;
   return true;
}

void RefreshSession()
{
   if(g_session_owner) GlobalVariableSet(SessionKey(),(double)TimeCurrent());
}

void ReleaseSession()
{
   if(g_session_owner && GlobalVariableCheck(SessionKey()))
      GlobalVariableDel(SessionKey());
   g_session_owner=false;
}

string JsonEscape(string s)
{
   StringReplace(s,"\\","\\\\");
   StringReplace(s,"\"","\\\"");
   return s;
}

void UpperInPlace(string &s)
{
   StringToUpper(s);
}

bool IsUsableSymbol(string symbol)
{
   if(StringLen(symbol)==0) return false;
   if(SymbolInfoDouble(symbol,SYMBOL_BID)>0) return true;
   if(!SymbolSelect(symbol,true)) return false;
   return (SymbolInfoDouble(symbol,SYMBOL_BID)>0);
}

bool IsExactAllowedSymbol(string symbol)
{
   return (symbol=="XAUUSDm" || symbol=="EURUSDm");
}

string NormalizeInstrumentKey(string s)
{
   UpperInPlace(s);
   StringReplace(s,"/","");
   StringReplace(s,"_","");
   StringReplace(s,"-","");
   StringReplace(s,".","");
   return s;
}

bool IsBlockedSource(string source)
{
   string x=source;
   StringToLower(x);
   StringReplace(x,"+"," ");
   StringReplace(x,"-"," ");
   StringReplace(x,"_"," ");
   while(StringFind(x,"  ")>=0) StringReplace(x,"  "," ");
   return (StringFind(x,"book")>=0 && StringFind(x,"openai")>=0);
}

string OrderGuardKey(string order_id)
{
   return "SignalX.guard."+IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN))+"."+order_id;
}

bool GuardAllows(string order_id)
{
   if(order_id=="") return false;
   string key=OrderGuardKey(order_id);
   if(!GlobalVariableCheck(key)) return true;
   double last=GlobalVariableGet(key);
   return (TimeCurrent()-((datetime)last)) >= DuplicateCooldownSeconds;
}

void MarkOrderGuard(string order_id)
{
   if(order_id!="") GlobalVariableSet(OrderGuardKey(order_id),(double)TimeCurrent());
}

bool ValidSignalLevels(string symbol,string dir,double sl,double tp)
{
   if(!IsExactAllowedSymbol(symbol) || !IsUsableSymbol(symbol)) return false;
   if(sl<=0 || tp<=0 || !MathIsValidNumber(sl) || !MathIsValidNumber(tp)) return false;
   MqlTick tick;
   if(!SymbolInfoTick(symbol,tick)) return false;
   double point=SymbolInfoDouble(symbol,SYMBOL_POINT);
   int stops=(int)SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL);
   double minDist=stops*point;
   if(dir=="BUY") return (sl < tick.bid-minDist && tp > tick.ask+minDist);
   if(dir=="SELL") return (sl > tick.ask+minDist && tp < tick.bid-minDist);
   return false;
}

double NormalizeVolume(string symbol,double requested)
{
   double minv=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN);
   double maxv=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX);
   double step=SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP);
   if(minv<=0 || maxv<=0 || step<=0) return 0.0;
   double v=requested>0 ? requested : DefaultLot;
   v=MathMax(minv,MathMin(maxv,v));
   v=MathFloor((v+1e-12)/step)*step;
   int digits=(int)MathMax(0,MathCeil(-MathLog10(step)));
   return NormalizeDouble(v,digits);
}

string ExecSymbol(string market)
{
   string m=market; UpperInPlace(m);
   string wanted=(StringFind(m,"EUR")>=0) ? EURTradeSymbol : XAUTradeSymbol;
   if(!IsExactAllowedSymbol(wanted) || !IsUsableSymbol(wanted)) return "";
   return wanted;
}

string XAUStateSymbol()
{
   return (XAUTradeSymbol=="XAUUSDm" && IsUsableSymbol(XAUTradeSymbol)) ? XAUTradeSymbol : "";
}

string EURStateSymbol()
{
   return (EURTradeSymbol=="EURUSDm" && IsUsableSymbol(EURTradeSymbol)) ? EURTradeSymbol : "";
}

string TFKey(ENUM_TIMEFRAMES tf)
{
   if(tf==PERIOD_M1)  return "1min";
   if(tf==PERIOD_M5)  return "5min";
   if(tf==PERIOD_M15) return "15min";
   if(tf==PERIOD_M30) return "30min";
   if(tf==PERIOD_H1)  return "1h";
   if(tf==PERIOD_H4)  return "4h";
   if(tf==PERIOD_D1)  return "1day";
   return EnumToString(tf);
}

string RatesJson(string symbol,ENUM_TIMEFRAMES tf,int count)
{
   MqlRates rates[];
   ArraySetAsSeries(rates,false);
   int copied=CopyRates(symbol,tf,0,count,rates);
   if(copied<=0) return "[]";

   string out="[";
   bool first=true;
   int start=copied-count;
   if(start<0) start=0;
   for(int i=start;i<copied;i++)
   {
      if(!first) out+=",";
      first=false;
      out += StringFormat(
         "{\"time\":%I64d,\"open\":%.10f,\"high\":%.10f,\"low\":%.10f,\"close\":%.10f}",
         (long)rates[i].time,
         rates[i].open,
         rates[i].high,
         rates[i].low,
         rates[i].close
      );
   }
   out+="]";
   return out;
}

string ClientId()
{
   if(StringLen(BridgeClientId)>0) return BridgeClientId;
   return "SignalX-"+IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN));
}

string UrlEncodeSimple(string s)
{
   StringReplace(s,"%","%25");
   StringReplace(s," ","%20");
   StringReplace(s,"/","%2F");
   StringReplace(s,"+","%2B");
   StringReplace(s,"#","%23");
   StringReplace(s,"?","%3F");
   StringReplace(s,"&","%26");
   return s;
}

int Http(string method,string url,string body,string &out)
{
   char data[];
   int data_size=0;
   if(StringLen(body)>0)
      data_size=StringToCharArray(body,data,0,StringLen(body),CP_UTF8);

   char result[];
   string headers="Content-Type: application/json\r\n";
   string result_headers="";
   ResetLastError();
   int code=WebRequest(method,url,headers,5000,data,result,result_headers);
   int err=GetLastError();
   out=CharArrayToString(result,0,-1,CP_UTF8);
   Print("[MT5 BRIDGE] ",method," ",url," -> HTTP=",code," LastError=",err," Response=",out);
   return code;
}

void AppendMarketState(string &body,string symbol,bool &firstMarket)
{
   if(!IsUsableSymbol(symbol)) return;
   if(!firstMarket) body+=",";
   firstMarket=false;

   ENUM_TIMEFRAMES tfs[7]={PERIOD_M1,PERIOD_M5,PERIOD_M15,PERIOD_M30,PERIOD_H1,PERIOD_H4,PERIOD_D1};

   body += "\""+JsonEscape(symbol)+"\":{";
   body += "\"connected\":true";
   body += ",\"account\":\""+IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN))+"\"";
   body += ",\"server\":\""+JsonEscape(AccountInfoString(ACCOUNT_SERVER))+"\"";
   body += ",\"balance\":"+DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),2);
   body += ",\"equity\":"+DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2);
   body += ",\"free_margin\":"+DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_FREE),2);
   body += ",\"margin\":"+DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN),2);
   body += ",\"positions\":"+IntegerToString(PositionsTotal());
   body += ",\"candles\":{";

   for(int i=0;i<7;i++)
   {
      if(i>0) body+=",";
      string key=TFKey(tfs[i]);
      body += "\""+key+"\":"+RatesJson(symbol,tfs[i],120);
   }
   body += "}}";
}

void ReportState()
{
   string xau=XAUStateSymbol();
   string eur=EURStateSymbol();

   string body="{";
   body += "\"connected\":true";
   body += ",\"symbol\":\"DUAL\"";
   body += ",\"login\":\""+IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN))+"\"";
   body += ",\"server\":\""+JsonEscape(AccountInfoString(ACCOUNT_SERVER))+"\"";
   body += ",\"balance\":"+DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),2);
   body += ",\"equity\":"+DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2);
   body += ",\"free_margin\":"+DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_FREE),2);
   body += ",\"margin\":"+DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN),2);
   body += ",\"positions\":"+IntegerToString(PositionsTotal());
   body += ",\"candles\":{}";
   body += ",\"markets\":{";

   bool firstMarket=true;
   AppendMarketState(body,xau,firstMarket);
   AppendMarketState(body,eur,firstMarket);
   body += "}}";

   string out;
   Http("POST",Url("/api/v1/mt5/state?token="+BridgeToken),body,out);
}

string ExtractString(string json,string key,int from_pos)
{
   string needle="\""+key+"\":\"";
   int p=StringFind(json,needle,from_pos);
   if(p<0) return "";
   int s=p+StringLen(needle);
   int e=StringFind(json,"\"",s);
   if(e<0) return "";
   return StringSubstr(json,s,e-s);
}

double ExtractNumber(string json,string key,int from_pos)
{
   string needle="\""+key+"\":";
   int p=StringFind(json,needle,from_pos);
   if(p<0) return 0.0;
   int s=p+StringLen(needle);
   int e=s;
   while(e<StringLen(json))
   {
      ushort c=StringGetCharacter(json,e);
      if((c>='0' && c<='9') || c=='-' || c=='+' || c=='.' || c=='e' || c=='E') e++;
      else break;
   }
   return StringToDouble(StringSubstr(json,s,e-s));
}

double ExtractFirstTP(string json,int from_pos)
{
   string needle="\"tp\":[";
   int p=StringFind(json,needle,from_pos);
   if(p<0) return 0.0;
   int s=p+StringLen(needle);
   int e=s;
   while(e<StringLen(json))
   {
      ushort c=StringGetCharacter(json,e);
      if((c>='0' && c<='9') || c=='-' || c=='+' || c=='.' || c=='e' || c=='E') e++;
      else break;
   }
   return StringToDouble(StringSubstr(json,s,e-s));
}

void SendReport(string order_id,string action,string status,string symbol,string message)
{
   string rb=StringFormat(
      "{\"action\":\"%s\",\"ticket\":\"%s\",\"symbol\":\"%s\",\"status\":\"%s\",\"message\":\"%s\",\"client_id\":\"%s\"}",
      JsonEscape(action),JsonEscape(order_id),JsonEscape(symbol),JsonEscape(status),JsonEscape(message),JsonEscape(ClientId())
   );
   string out;
   Http("POST",Url("/api/v1/mt5/report?token="+BridgeToken),rb,out);
}

int OnInit()
{
   if(ApiBase=="" || StringFind(ApiBase,"http")!=0) return(INIT_PARAMETERS_INCORRECT);
   if(BridgeToken=="" || BridgeToken=="CHANGE_ME") return(INIT_PARAMETERS_INCORRECT);
   if(XAUTradeSymbol!="XAUUSDm" || EURTradeSymbol!="EURUSDm") return(INIT_PARAMETERS_INCORRECT);
   if(!AcquireSession()) return(INIT_FAILED);
   trade.SetExpertMagicNumber(SignalXMagic);
   trade.SetAsyncMode(false);
   Print("[MT5 BRIDGE] STARTED chart=",_Symbol," ApiBase=",ApiBase," PollSeconds=",PollSeconds," Lot=",DoubleToString(DefaultLot,2)," Magic=",SignalXMagic);
   Print("[MT5 BRIDGE] Broker-safe execution: arbitrage/latency/bonus-abuse logic disabled; exact symbols only.");
   Print("[MT5 BRIDGE] WebRequest allow URL: ",ApiBase);
   Print("[MT5 BRIDGE] ClientId=",ClientId());
   EventSetTimer(MathMax(1,PollSeconds));
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   ReleaseSession();
   Print("[MT5 BRIDGE] STOPPED reason=",reason);
}

bool PollMarket(string requestedMarket,string expectedSymbol)
{
   string out;
   string encoded=requestedMarket;
   StringReplace(encoded,"/","%2F");
   int code=Http("GET",Url("/api/v1/mt5/poll?token="+BridgeToken+"&market="+encoded+"&client_id="+UrlEncodeSimple(ClientId())),"",out);
   if(code!=200)
   {
      Print("[MT5 BRIDGE] POLL FAILED market=",requestedMarket," HTTP=",code);
      return false;
   }

   if(StringFind(out,"\"orders\":[]")>=0)
   {
      Print("[MT5 BRIDGE] POLL RECEIVED market=",requestedMarket," orders=0");
      return true;
   }

   Print("[MT5 BRIDGE] POLL RECEIVED market=",requestedMarket," response_len=",StringLen(out));
   int pos=0;
   while((pos=StringFind(out,"\"id\":\"",pos))>=0)
   {
      string order_id=ExtractString(out,"id",pos);
      string dir=ExtractString(out,"direction",pos);
      string requested_symbol=ExtractString(out,"symbol",pos);
      string order_market=ExtractString(out,"market",pos);
      string source=ExtractString(out,"source",pos);
      double entry=ExtractNumber(out,"entry",pos);
      double sl=ExtractNumber(out,"sl",pos);
      double tp=ExtractFirstTP(out,pos);
      double vol=ExtractNumber(out,"volume",pos);
      Print("[AUTO TRADE] RECEIVED order_id=",order_id," market=",order_market," symbol=",requested_symbol," direction=",dir," entry=",DoubleToString(entry,5)," sl=",DoubleToString(sl,5)," tp=",DoubleToString(tp,5)," source=",source);
      if(vol<=0) vol=DefaultLot;

      if(IsBlockedSource(source))
      {
         SendReport(order_id,dir,"ORDER_FAILED",expectedSymbol,"BLOCKED: Book + OpenAI source is excluded from AutoTrade");
         pos+=MathMax(1,StringLen(order_id));
         continue;
      }
      if(!GuardAllows(order_id))
      {
         Print("[MT5 BRIDGE] duplicate/cooldown blocked order_id=",order_id);
         pos+=MathMax(1,StringLen(order_id));
         continue;
      }

      string req=requested_symbol;
      string mkt=order_market;
      string expected=expectedSymbol;
      string reqKey=NormalizeInstrumentKey(req);
      string mktKey=NormalizeInstrumentKey(mkt);
      string expectedKey=NormalizeInstrumentKey(expected);

      bool isEUR=(StringFind(NormalizeInstrumentKey(requestedMarket),"EUR")>=0);
      string expectedMarketKey=isEUR ? "EURUSD" : "XAUUSD";
      bool marketMatches=(mktKey==expectedMarketKey || StringFind(mktKey,expectedMarketKey)>=0);
      bool symbolMatches=(reqKey==expectedMarketKey || StringFind(reqKey,expectedMarketKey)>=0);
      bool expectedMatches=(expectedKey==expectedMarketKey || StringFind(expectedKey,expectedMarketKey)>=0);
      if(!marketMatches || !symbolMatches || !expectedMatches)
      {
         string msg=StringFormat("BLOCKED: cross-symbol order rejected by EA req=%s market=%s expected=%s",reqKey,mktKey,expectedKey);
         Print("[AUTO TRADE] ORDER_FAILED order_id=",order_id," ",msg);
         SendReport(order_id,dir,"ORDER_FAILED",expectedSymbol,msg);
         pos+=MathMax(1,StringLen(order_id));
         continue;
      }

      string execSymbol=ExecSymbol(requestedMarket);

      if(StringLen(execSymbol)==0)
      {
         SendReport(order_id,dir,"ORDER_FAILED",expectedSymbol,"Symbol not available");
         pos+=MathMax(1,StringLen(order_id));
         continue;
      }

      // Broker-safe layer rejects malformed execution levels and duplicate IDs.
      vol=NormalizeVolume(execSymbol,vol);
      if(vol<=0)
      {
         SendReport(order_id,dir,"ORDER_FAILED",execSymbol,"BLOCKED: invalid broker volume");
         MarkOrderGuard(order_id);
         pos+=MathMax(1,StringLen(order_id));
         continue;
      }
      if(!ValidSignalLevels(execSymbol,dir,sl,tp))
      {
         SendReport(order_id,dir,"ORDER_FAILED",execSymbol,"BLOCKED: invalid/stale SL/TP relative to live broker price");
         MarkOrderGuard(order_id);
         pos+=MathMax(1,StringLen(order_id));
         continue;
      }

      // Explicitly surface terminal/account trade permissions before sending.
      if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
      {
         string msg="BLOCKED: MT5 terminal AutoTrading is disabled";
         Print("[AUTO TRADE] ORDER_FAILED order_id=",order_id," ",msg);
         SendReport(order_id,dir,"ORDER_FAILED",execSymbol,msg);
         pos+=MathMax(1,StringLen(order_id));
         continue;
      }
      if(!MQLInfoInteger(MQL_TRADE_ALLOWED))
      {
         string msg="BLOCKED: EA trading permission is disabled";
         Print("[AUTO TRADE] ORDER_FAILED order_id=",order_id," ",msg);
         SendReport(order_id,dir,"ORDER_FAILED",execSymbol,msg);
         pos+=MathMax(1,StringLen(order_id));
         continue;
      }
      if(!AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))
      {
         string msg="BLOCKED: account trading is disabled";
         Print("[AUTO TRADE] ORDER_FAILED order_id=",order_id," ",msg);
         SendReport(order_id,dir,"ORDER_FAILED",execSymbol,msg);
         pos+=MathMax(1,StringLen(order_id));
         continue;
      }
      if(!AccountInfoInteger(ACCOUNT_TRADE_EXPERT))
      {
         string msg="BLOCKED: broker disallows Expert Advisor trading on this account";
         Print("[AUTO TRADE] ORDER_FAILED order_id=",order_id," ",msg);
         SendReport(order_id,dir,"ORDER_FAILED",execSymbol,msg);
         pos+=MathMax(1,StringLen(order_id));
         continue;
      }

      MqlTick liveTick;
      if(!SymbolInfoTick(execSymbol,liveTick))
      {
         string msg="BLOCKED: live broker tick unavailable";
         Print("[AUTO TRADE] ORDER_FAILED order_id=",order_id," ",msg);
         SendReport(order_id,dir,"ORDER_FAILED",execSymbol,msg);
         pos+=MathMax(1,StringLen(order_id));
         continue;
      }

      trade.SetTypeFillingBySymbol(execSymbol);
      trade.SetDeviationInPoints(20);
      string comment="SignalX "+(source==""?"AUTO":source);
      bool ok=false;
      if(dir=="BUY")  ok=trade.Buy(vol,execSymbol,0,sl,tp,comment);
      else if(dir=="SELL") ok=trade.Sell(vol,execSymbol,0,sl,tp,comment);
      else
      {
         string msg="BLOCKED: invalid direction "+dir;
         Print("[AUTO TRADE] ORDER_FAILED order_id=",order_id," ",msg);
         SendReport(order_id,dir,"ORDER_FAILED",execSymbol,msg);
         pos+=MathMax(1,StringLen(order_id));
         continue;
      }

      uint retcode=trade.ResultRetcode();
      string desc=trade.ResultRetcodeDescription();
      ulong deal=trade.ResultDeal();
      ulong ord=trade.ResultOrder();
      bool brokerAccepted=(retcode==TRADE_RETCODE_DONE || retcode==TRADE_RETCODE_DONE_PARTIAL || retcode==TRADE_RETCODE_PLACED);
      Print("[AUTO TRADE] EXECUTION order_id=",order_id,
            " symbol=",execSymbol,
            " volume=",DoubleToString(vol,2),
            " bid=",DoubleToString(liveTick.bid,SymbolInfoInteger(execSymbol,SYMBOL_DIGITS)),
            " ask=",DoubleToString(liveTick.ask,SymbolInfoInteger(execSymbol,SYMBOL_DIGITS)),
            " request_ok=",ok?"true":"false",
            " broker_accepted=",brokerAccepted?"true":"false",
            " retcode=",retcode,
            " desc=",desc,
            " deal=",(long)deal,
            " order=",(long)ord);
      MarkOrderGuard(order_id);
      if(brokerAccepted)
      {
         Print("[AUTO TRADE] ORDER_SENT order_id=",order_id," symbol=",execSymbol," retcode=",retcode," deal=",(long)deal," order=",(long)ord);
         SendReport(order_id,dir,"ORDER_SENT",execSymbol,StringFormat("retcode=%u deal=%I64u order=%I64u %s",retcode,deal,ord,desc));
      }
      else
      {
         Print("[AUTO TRADE] ORDER_FAILED order_id=",order_id," symbol=",execSymbol," retcode=",retcode," desc=",desc);
         SendReport(order_id,dir,"ORDER_FAILED",execSymbol,StringFormat("retcode=%u deal=%I64u order=%I64u %s",retcode,deal,ord,desc));
      }

      pos+=MathMax(1,StringLen(order_id));
   }
   return true;
}

void OnTimer()
{
   RefreshSession();
   if(g_last_state==0 || (TimeCurrent()-g_last_state)>=StateSeconds)
   {
      ReportState();
      g_last_state=TimeCurrent();
   }

   string xau=XAUStateSymbol();
   string eur=EURStateSymbol();
   PollMarket("XAU/USD",xau);
   PollMarket("EUR/USD",eur);
}
