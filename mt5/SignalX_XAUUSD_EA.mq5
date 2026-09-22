#property strict
#property version   "1.8"
#property description "SignalX XAUUSD MT5 bridge"

#include <Trade/Trade.mqh>
CTrade trade;

input string ApiBase="https://signalx.asia";
input string BridgeToken="PASTE_MT5_BRIDGE_TOKEN";
input int    PollSeconds=2;
input int    StateSeconds=5;
input double DefaultLot=0.01;
input string XAUTradeSymbol="XAUUSDm";
input long   SignalXMagic=26091401;
input int    DuplicateCooldownSeconds=30;
input int    MaxDeviationPoints=100; // wider XAU execution tolerance for normal market movement
input int    ExecutionRetries=2; // retry transient price/quote errors only
input int    MaxSpreadPoints=80; // XAUUSDm maximum bid/ask spread in points
input string BridgeClientId=""; // blank = account-specific client id
input bool   SingleSession=true; // only one EA instance per MT5 terminal/account
input int    SessionLeaseSeconds=15;
input int    MaxOpenPositionsPerSymbol=3; // Aggregate limit across all nine SignalX modules

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

double NormalizePrice(string symbol,double price)
{
   if(price<=0 || !MathIsValidNumber(price)) return 0.0;
   double tick_size=SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_SIZE);
   int digits=(int)SymbolInfoInteger(symbol,SYMBOL_DIGITS);
   if(tick_size>0) price=MathRound(price/tick_size)*tick_size;
   return NormalizeDouble(price,digits);
}



bool SymbolSessionOpenNow(string symbol, string &source)
{
   source="MT5_SYMBOL_TRADE_SESSION";
   if(symbol=="") return false;
   datetime now=TimeTradeServer();
   if(now<=0) now=TimeCurrent();
   MqlDateTime dt;
   TimeToStruct(now,dt);
   int current_min=dt.hour*60+dt.min;
   ENUM_DAY_OF_WEEK dow=(ENUM_DAY_OF_WEEK)dt.day_of_week;
   bool found=false;
   for(uint i=0;i<20;i++)
   {
      datetime from=0,to=0;
      ResetLastError();
      if(!SymbolInfoSessionTrade(symbol,dow,i,from,to)) break;
      found=true;
      int from_min=TimeHour(from)*60+TimeMinute(from);
      int to_min=TimeHour(to)*60+TimeMinute(to);
      bool open=false;
      if(from_min<=to_min)
         open=(current_min>=from_min && current_min<to_min);
      else
         open=(current_min>=from_min || current_min<to_min);
      if(open) return true;
   }
   return false;
}

string SessionStateJson(string symbol)
{
   string source="MT5_SYMBOL_TRADE_SESSION";
   bool open=SymbolSessionOpenNow(symbol,source);
   datetime now=TimeTradeServer();
   if(now<=0) now=TimeCurrent();
   string out=",\"session_open\":"+(open?"true":"false");
   out+=",\"session_source\":\""+JsonEscape(source)+"\"";
   out+=",\"server_time\":\""+JsonEscape(TimeToString(now,TIME_DATE|TIME_SECONDS))+"\"";
   return out;
}

bool IsUsableSymbol(string symbol)
{
   if(StringLen(symbol)==0) return false;
   if(SymbolInfoDouble(symbol,SYMBOL_BID)>0) return true;
   if(!SymbolSelect(symbol,true)) return false;
   return (SymbolInfoDouble(symbol,SYMBOL_BID)>0);
}

string Compact(string symbol)
{
   string c=symbol;
   StringToUpper(c);
   StringReplace(c,"/","");
   StringReplace(c,"-","");
   StringReplace(c,"_","");
   StringReplace(c,".","");
   return c;
}

string Canonical(string symbol)
{
   string c=Compact(symbol);
   if(StringFind(c,"XAUUSD")>=0) return "XAU/USD";
   return symbol;
}

bool IsExactAllowedSymbol(string symbol)
{
   return (Canonical(symbol)=="XAU/USD");
}

string FindBrokerXAU()
{
   // Prefer the configured symbol, then discover broker suffix/prefix variants.
   if(IsExactAllowedSymbol(XAUTradeSymbol) && IsUsableSymbol(XAUTradeSymbol))
      return XAUTradeSymbol;
   int total=SymbolsTotal(false);
   for(int i=0;i<total;i++)
   {
      string s=SymbolName(i,false);
      if(Canonical(s)=="XAU/USD" && IsUsableSymbol(s)) return s;
   }
   return "";
}

bool IsBlockedSource(string source)
{
   string x=source;
   StringToLower(x);
   StringTrimLeft(x); StringTrimRight(x);
   return !(x=="ict ai pro" || x=="snr" || x=="ai analysis" || x=="trend" ||
            x=="trend liniya" || x=="technical analysis" || x=="classic trade" ||
            x=="ob trade" || x=="fibonacci trade");
}

bool ValidExecutionRR(string symbol,string direction,string orderType,double entry,double sl,double tp)
{
   MqlTick tick;
   if(!SymbolInfoTick(symbol,tick)) return false;
   double point=SymbolInfoDouble(symbol,SYMBOL_POINT);
   double fill=entry;
   if(orderType=="MARKET")
      fill=(direction=="BUY" ? tick.ask+MaxDeviationPoints*point : tick.bid-MaxDeviationPoints*point);
   if(!MathIsValidNumber(fill) || !MathIsValidNumber(sl) || !MathIsValidNumber(tp) || fill<=0 || sl<=0 || tp<=0) return false;
   double risk=(direction=="BUY" ? fill-sl : sl-fill);
   double reward=(direction=="BUY" ? tp-fill : fill-tp);
   return (risk>0 && reward>0 && reward/risk>=1.0-0.00000001);
}

string OrderGuardKey(string order_id)
{
   return "SignalX.guard."+IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN))+"."+order_id;
}

bool GuardAllows(string order_id)
{
   if(order_id=="") return false;
   if(GlobalVariableCheck(OrderGuardKey(order_id)+".done")) return false;
   string key=OrderGuardKey(order_id);
   if(!GlobalVariableCheck(key)) return true;
   double last=GlobalVariableGet(key);
   return (TimeCurrent()-((datetime)last)) >= DuplicateCooldownSeconds;
}

void MarkOrderGuard(string order_id)
{
   if(order_id!="") GlobalVariableSet(OrderGuardKey(order_id),(double)TimeCurrent());
}


int CountSignalXPositions(string symbol)
{
   int count=0;
   for(int i=0;i<PositionsTotal();i++)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL)==symbol && PositionGetInteger(POSITION_MAGIC)==SignalXMagic) count++;
   }
   return count;
}

bool HasEnoughMargin(string symbol,string dir,double volume)
{
   MqlTick tick;
   if(!SymbolInfoTick(symbol,tick)) return false;
   double margin=0.0;
   ENUM_ORDER_TYPE type=(dir=="BUY" ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
   double price=(dir=="BUY" ? tick.ask : tick.bid);
   if(!OrderCalcMargin(type,symbol,volume,price,margin)) return false;
   return (margin>0.0 && AccountInfoDouble(ACCOUNT_MARGIN_FREE)>=margin);
}

bool ValidSignalLevels(string symbol,string dir,double sl,double tp)
{
   if(!IsExactAllowedSymbol(symbol) || !IsUsableSymbol(symbol)) return false;
   if(sl<=0 || tp<=0 || !MathIsValidNumber(sl) || !MathIsValidNumber(tp)) return false;
   sl=NormalizePrice(symbol,sl);
   tp=NormalizePrice(symbol,tp);
   MqlTick tick;
   if(!SymbolInfoTick(symbol,tick)) return false;
   double point=SymbolInfoDouble(symbol,SYMBOL_POINT);
   double tick_size=SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_SIZE);
   if(tick_size<=0) tick_size=point;
   int stops=(int)SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL);
   int freeze=(int)SymbolInfoInteger(symbol,SYMBOL_TRADE_FREEZE_LEVEL);
   double minDist=MathMax(stops,freeze)*point;
   if(minDist<tick_size) minDist=tick_size;
   if(dir=="BUY") return (sl <= tick.bid-minDist && tp >= tick.ask+minDist);
   if(dir=="SELL") return (sl >= tick.ask+minDist && tp <= tick.bid-minDist);
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
   if(market!="" && IsExactAllowedSymbol(market) && IsUsableSymbol(market)) return market;
   return FindBrokerXAU();
}

string XAUStateSymbol()
{
   return FindBrokerXAU();
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
   body += SessionStateJson(symbol);
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

   string body="{";
   body += "\"connected\":true";
   body += ",\"symbol\":\""+JsonEscape(xau)+"\"";
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

bool IsPendingOrderType(string orderType)
{
   return orderType=="BUY_STOP" || orderType=="SELL_STOP" ||
          orderType=="BUY_LIMIT" || orderType=="SELL_LIMIT";
}

bool PendingEntryValid(string symbol,string orderType,double entry)
{
   if(!IsPendingOrderType(orderType) || entry<=0 || !MathIsValidNumber(entry)) return false;
   MqlTick tick;
   if(!SymbolInfoTick(symbol,tick)) return false;
   double point=SymbolInfoDouble(symbol,SYMBOL_POINT);
   double tickSize=SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_SIZE);
   if(point<=0) return false;
   if(tickSize<=0) tickSize=point;
   entry=NormalizePrice(symbol,entry);
   int stops=(int)SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL);
   int freeze=(int)SymbolInfoInteger(symbol,SYMBOL_TRADE_FREEZE_LEVEL);
   double minDist=MathMax(stops,freeze)*point;
   if(minDist<tickSize) minDist=tickSize;
   if(orderType=="BUY_STOP") return entry>=tick.ask+minDist;
   if(orderType=="SELL_STOP") return entry<=tick.bid-minDist;
   if(orderType=="BUY_LIMIT") return entry<=tick.ask-minDist;
   if(orderType=="SELL_LIMIT") return entry>=tick.bid+minDist;
   return false;
}

bool CancelPendingBySignalId(string orderId)
{
   bool found=false;
   for(int i=OrdersTotal()-1;i>=0;i--)
   {
      ulong ticket=OrderGetTicket(i);
      if(ticket==0) continue;
      if(OrderGetInteger(ORDER_MAGIC)!=SignalXMagic) continue;
      ENUM_ORDER_TYPE type=(ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);
      bool pending=(type==ORDER_TYPE_BUY_LIMIT || type==ORDER_TYPE_SELL_LIMIT ||
                    type==ORDER_TYPE_BUY_STOP || type==ORDER_TYPE_SELL_STOP ||
                    type==ORDER_TYPE_BUY_STOP_LIMIT || type==ORDER_TYPE_SELL_STOP_LIMIT);
      if(!pending) continue;
      string comment=OrderGetString(ORDER_COMMENT);
      if(StringFind(comment,orderId)<0) continue;
      if(trade.OrderDelete(ticket))
      {
         found=true;
         Print("[MT5 BRIDGE] PENDING CANCELLED order_id=",orderId," ticket=",ticket);
      }
   }
   return found;
}

void ProcessCancelCommands(string json)
{
   int scan=0;
   while((scan=StringFind(json,"\"cancel_orders\":[",scan))>=0)
   {
      int p=StringFind(json,"{",scan);
      if(p<0) break;
      int e=StringFind(json,"}",p);
      if(e<0) break;
      string c=StringSubstr(json,p,e-p+1);
      string id=ExtractString(c,"id",0);
      if(id=="") id=ExtractString(c,"order_id",0);
      if(id!="")
      {
         CancelPendingBySignalId(id);
         SendReport(id,"CANCEL","CANCELLED","", "Pending setup cancelled by SignalX");
      }
      scan=e+1;
   }
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
   if(FindBrokerXAU()=="") return(INIT_PARAMETERS_INCORRECT);
   if(!AcquireSession()) return(INIT_FAILED);
   trade.SetExpertMagicNumber(SignalXMagic);
   trade.SetAsyncMode(false);
   Print("[MT5 BRIDGE] STARTED chart=",_Symbol," ApiBase=",ApiBase," PollSeconds=",PollSeconds," Lot=",DoubleToString(DefaultLot,2)," Magic=",SignalXMagic," Deviation=",MaxDeviationPoints," Retries=",ExecutionRetries);
   Print("[MT5 BRIDGE] Broker-safe execution: arbitrage/latency/bonus-abuse logic disabled; exact symbols only.");
   Print("[MT5 BRIDGE] WebRequest allow URL: ",ApiBase);
   Print("[MT5 BRIDGE] ClientId=",ClientId());
   EventSetTimer(MathMax(1,PollSeconds));
   return(INIT_SUCCEEDED);
}


// --- SignalX TP1/TP2 partial-close lifecycle ---
string SXTP1Key(string order_id) { return "SignalX.TP1."+IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN))+"."+order_id; }
string SXTP2Key(string order_id) { return "SignalX.TP2."+IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN))+"."+order_id; }
string SXTPDoneKey(ulong ticket) { return "SignalX.TP1DONE."+IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN))+"."+IntegerToString((long)ticket); }

double SXNormalizeVolume(double v,string symbol)
{
   double vmin=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN);
   double vmax=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX);
   double step=SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP);
   if(step<=0) step=vmin;
   if(step<=0) return 0;
   v=MathMin(v,vmax);
   v=MathFloor(v/step+1e-9)*step;
   int digits=0; double x=step;
   while(digits<8 && MathAbs(x-MathRound(x))>1e-9){x*=10.0;digits++;}
   return NormalizeDouble(v,digits);
}

void SXStoreTPLevels(string order_id,double tp1,double tp2)
{
   if(order_id=="" || tp1<=0 || tp2<=0) return;
   GlobalVariableSet(SXTP1Key(order_id),tp1);
   GlobalVariableSet(SXTP2Key(order_id),tp2);
}

bool SXGetOrderIdFromComment(string comment,string &order_id)
{
   int p=StringFind(comment,"SignalX ");
   if(p<0) return false;
   int a=p+8;
   int e=StringFind(comment," ",a);
   if(e<0) order_id=StringSubstr(comment,a);
   else order_id=StringSubstr(comment,a,e-a);
   return order_id!="";
}

void SXHandleTP1TP2()
{
   if(!EnableTP1PartialClose) return;

   for(int i=PositionsTotal()-1;i>=0;--i)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !PositionSelectByTicket(ticket)) continue;

      string symbol=PositionGetString(POSITION_SYMBOL);
      string comment=PositionGetString(POSITION_COMMENT);
      string order_id="";
      if(!SXGetOrderIdFromComment(comment,order_id)) continue;

      string k1=SXTP1Key(order_id), k2=SXTP2Key(order_id), kd=SXTP1DoneKey(ticket);
      if(!GlobalVariableCheck(k1) || !GlobalVariableCheck(k2) || GlobalVariableCheck(kd)) continue;

      double tp1=GlobalVariableGet(k1);
      double tp2=GlobalVariableGet(k2);
      if(tp1<=0 || tp2<=0) continue;

      long type=PositionGetInteger(POSITION_TYPE);
      double bid=SymbolInfoDouble(symbol,SYMBOL_BID);
      double ask=SymbolInfoDouble(symbol,SYMBOL_ASK);
      bool reached=(type==POSITION_TYPE_BUY ? bid>=tp1 : ask<=tp1);
      if(!reached) continue;

      double volume=PositionGetDouble(POSITION_VOLUME);
      double vmin=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN);

      // SignalX rule:
      // > minimum lot: close 75% at TP1; keep 25% for TP2.
      // SL is moved to the original entry (break-even) after TP1.
      // A 0.01 minimum position cannot be split below broker minimum,
      // so it is handled as a single TP1-final position.
      bool is_min_lot=(volume <= vmin + 1e-9);
      double closeVol=0.0;

      if(!is_min_lot)
         closeVol=SXNormalizeVolume(volume*0.75,symbol);

      bool action_ok=false;

      if(is_min_lot || closeVol<=0.0 || (volume-closeVol)<vmin)
      {
         // Broker minimum lot cannot leave a valid 25% remainder.
         // TP1 is therefore the effective final target for this minimum lot.
         action_ok=true;
      }
      else
      {
         ResetLastError();
         action_ok=trade.PositionClosePartial(ticket,closeVol);
      }

      if(action_ok)
      {
         double entry=PositionGetDouble(POSITION_PRICE_OPEN);
         double be=NormalizePrice(symbol,entry);

         if(is_min_lot)
         {
            if(PositionSelectByTicket(ticket))
               trade.PositionModify(ticket,be,tp1);
         }
         else
         {
            // Remaining 25% continues to TP2; SL is now at break-even.
            if(PositionSelectByTicket(ticket))
               trade.PositionModify(ticket,be,tp2);
         }

         GlobalVariableSet(kd,1.0);
      }
   }
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
   ProcessCancelCommands(out);
   int pos=0;
   while((pos=StringFind(out,"\"id\":\"",pos))>=0)
   {
      string order_id=ExtractString(out,"id",pos);
      string dir=ExtractString(out,"direction",pos);
      string requested_symbol=ExtractString(out,"symbol",pos);
      string order_market=ExtractString(out,"market",pos);
      string source=ExtractString(out,"source",pos);
      string order_type=ExtractString(out,"order_type",pos);
      if(order_type=="") order_type="MARKET";
      UpperInPlace(order_type);
      double entry=ExtractNumber(out,"entry",pos);
      double sl=ExtractNumber(out,"sl",pos);
      double tp=ExtractFirstTP(out,pos);
       double tp1=ExtractNumber(out,"tp1",pos);
       double tp2=ExtractNumber(out,"tp2",pos);
       if(tp2<=0) tp2=tp;
       if(tp<=0) tp=tp2;
      double vol=ExtractNumber(out,"volume",pos);
      Print("[AUTO TRADE] RECEIVED order_id=",order_id," market=",order_market," symbol=",requested_symbol," direction=",dir," entry=",DoubleToString(entry,5)," sl=",DoubleToString(sl,5)," tp=",DoubleToString(tp,5)," source=",source);
      if(vol<=0) vol=DefaultLot;

      if(IsBlockedSource(source))
      {
         SendReport(order_id,dir,"ORDER_FAILED",expectedSymbol,"BLOCKED: source outside the nine-module allowlist");
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
      UpperInPlace(req);
      UpperInPlace(mkt);
      UpperInPlace(expected);

      bool marketMatches=(Canonical(mkt)=="XAU/USD");
      bool symbolMatches=(Canonical(req)=="XAU/USD");
      if(!marketMatches || !symbolMatches)
      {
         SendReport(order_id,dir,"ORDER_FAILED",expectedSymbol,"BLOCKED: cross-symbol order rejected by EA");
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
      if(MaxOpenPositionsPerSymbol>0 && CountSignalXPositions(execSymbol)>=MaxOpenPositionsPerSymbol)
      {
         string msg="BLOCKED: max open SignalX positions reached";
         Print("[AUTO TRADE] ORDER_FAILED order_id=",order_id," ",msg);
         SendReport(order_id,dir,"ORDER_FAILED",execSymbol,msg);
         pos+=MathMax(1,StringLen(order_id));
         continue;
      }
      if(!HasEnoughMargin(execSymbol,dir,vol))
      {
         string msg="BLOCKED: insufficient free margin";
         Print("[AUTO TRADE] ORDER_FAILED order_id=",order_id," ",msg);
         SendReport(order_id,dir,"ORDER_FAILED",execSymbol,msg);
         pos+=MathMax(1,StringLen(order_id));
         continue;
      }
      // Normalize execution prices to the broker's tick size/digits before validation and send.
      sl=NormalizePrice(execSymbol,sl);
      tp=NormalizePrice(execSymbol,tp);
      if(!ValidSignalLevels(execSymbol,dir,sl,tp))
      {
         MqlTick checkTick;
         SymbolInfoTick(execSymbol,checkTick);
         int digs=(int)SymbolInfoInteger(execSymbol,SYMBOL_DIGITS);
         string msg=StringFormat("BLOCKED: invalid/stale SL/TP bid=%.*f ask=%.*f sl=%.*f tp=%.*f stops=%d freeze=%d",
                                 digs,checkTick.bid,digs,checkTick.ask,digs,sl,digs,tp,
                                 (int)SymbolInfoInteger(execSymbol,SYMBOL_TRADE_STOPS_LEVEL),
                                 (int)SymbolInfoInteger(execSymbol,SYMBOL_TRADE_FREEZE_LEVEL));
         Print("[AUTO TRADE] ORDER_FAILED order_id=",order_id," ",msg);
         SendReport(order_id,dir,"ORDER_FAILED",execSymbol,msg);
         // Do not poison the local duplicate guard for a price/level validation failure.
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

      string comment="SignalX "+order_id+" "+(source==""?"AUTO":source);
      bool ok=false;
      uint retcode=0;
      string desc="";
      ulong deal=0;
      ulong ord=0;
      bool brokerAccepted=false;
      int attempts=MathMax(1,MathMin(3,ExecutionRetries));

      double spread_points=(liveTick.ask-liveTick.bid)/SymbolInfoDouble(execSymbol,SYMBOL_POINT);
      if(MaxSpreadPoints>0 && spread_points>MaxSpreadPoints)
      {
         string msg=StringFormat("BLOCKED: spread %.1f points > max %d",spread_points,MaxSpreadPoints);
         Print("[AUTO TRADE] ORDER_FAILED order_id=",order_id," ",msg);
         SendReport(order_id,dir,"ORDER_FAILED",execSymbol,msg);
         pos+=MathMax(1,StringLen(order_id));
         continue;
      }

      if(dir!="BUY" && dir!="SELL")
      {
         string msg="BLOCKED: invalid direction "+dir;
         Print("[AUTO TRADE] ORDER_FAILED order_id=",order_id," ",msg);
         SendReport(order_id,dir,"ORDER_FAILED",execSymbol,msg);
         pos+=MathMax(1,StringLen(order_id));
         continue;
      }

      for(int attempt=0; attempt<attempts; attempt++)
      {
         if(!SymbolInfoTick(execSymbol,liveTick))
         {
            desc="live broker tick unavailable";
            retcode=TRADE_RETCODE_PRICE_OFF;
            break;
         }
         sl=NormalizePrice(execSymbol,sl);
         tp=NormalizePrice(execSymbol,tp);
         tp2=tp; // Execute the exact TP used for the RR check, never a hidden target.
         if(!ValidExecutionRR(execSymbol,dir,order_type,entry,sl,tp))
         {
            desc="BLOCKED: final broker reward/risk below 1 or invalid geometry";
            retcode=TRADE_RETCODE_INVALID_STOPS;
            break;
         }
         if(!ValidSignalLevels(execSymbol,dir,sl,tp))
         {
            desc="SL/TP became invalid against refreshed broker price";
            retcode=TRADE_RETCODE_INVALID_STOPS;
            break;
         }
         if(!HasEnoughMargin(execSymbol,dir,vol))
         {
            desc="Insufficient free margin";
            retcode=TRADE_RETCODE_NO_MONEY;
            break;
         }

         trade.SetTypeFillingBySymbol(execSymbol);
         trade.SetDeviationInPoints(MaxDeviationPoints);
         if(IsPendingOrderType(order_type))
         {
            if(!PendingEntryValid(execSymbol,order_type,entry))
            {
               desc="Invalid pending entry against current bid/ask/stops";
               retcode=TRADE_RETCODE_INVALID_PRICE;
               break;
            }
            double expiry_epoch=ExtractNumber(out,"expiry_epoch",pos);
            datetime expiry=(expiry_epoch>0 ? (datetime)expiry_epoch : TimeCurrent()+900);
            ENUM_ORDER_TYPE_TIME tt=(expiry>TimeCurrent() ? ORDER_TIME_SPECIFIED : ORDER_TIME_GTC);
            datetime ex=(tt==ORDER_TIME_SPECIFIED ? expiry : 0);
            if(order_type=="BUY_STOP") ok=trade.BuyStop(vol,entry,execSymbol,sl,tp2,tt,ex,comment);
            else if(order_type=="SELL_STOP") ok=trade.SellStop(vol,entry,execSymbol,sl,tp2,tt,ex,comment);
            else if(order_type=="BUY_LIMIT") ok=trade.BuyLimit(vol,entry,execSymbol,sl,tp2,tt,ex,comment);
            else if(order_type=="SELL_LIMIT") ok=trade.SellLimit(vol,entry,execSymbol,sl,tp2,tt,ex,comment);
         }
         else
         {
            if(dir=="BUY") ok=trade.Buy(vol,execSymbol,0,sl,tp2,comment);
            else ok=trade.Sell(vol,execSymbol,0,sl,tp2,comment);
         }

         if(ok) SXStoreTPLevels(order_id,tp1,tp2);
          retcode=trade.ResultRetcode();
         desc=trade.ResultRetcodeDescription();
         deal=trade.ResultDeal();
         ord=trade.ResultOrder();
         brokerAccepted=(retcode==TRADE_RETCODE_DONE || retcode==TRADE_RETCODE_DONE_PARTIAL || retcode==TRADE_RETCODE_PLACED);
         Print("[AUTO TRADE] ATTEMPT order_id=",order_id,
               " #",attempt+1,"/",attempts,
               " symbol=",execSymbol,
               " dir=",dir,
               " vol=",DoubleToString(vol,2),
               " bid=",DoubleToString(liveTick.bid,SymbolInfoInteger(execSymbol,SYMBOL_DIGITS)),
               " ask=",DoubleToString(liveTick.ask,SymbolInfoInteger(execSymbol,SYMBOL_DIGITS)),
               " sl=",DoubleToString(sl,SymbolInfoInteger(execSymbol,SYMBOL_DIGITS)),
               " tp=",DoubleToString(tp,SymbolInfoInteger(execSymbol,SYMBOL_DIGITS)),
               " request_ok=",ok?"true":"false",
               " retcode=",retcode,
               " desc=",desc);
         if(brokerAccepted) break;

         bool transient=(retcode==TRADE_RETCODE_REQUOTE ||
                          retcode==TRADE_RETCODE_PRICE_CHANGED ||
                          retcode==TRADE_RETCODE_PRICE_OFF);
         if(!transient || attempt+1>=attempts) break;
         Sleep(150);
      }

      Print("[AUTO TRADE] EXECUTION order_id=",order_id,
            " symbol=",execSymbol,
            " request_ok=",ok?"true":"false",
            " broker_accepted=",brokerAccepted?"true":"false",
            " retcode=",retcode,
            " desc=",desc,
            " deal=",(long)deal,
            " order=",(long)ord);
      if(brokerAccepted)
      {
         GlobalVariableSet(OrderGuardKey(order_id)+".done",(double)TimeCurrent());
         MarkOrderGuard(order_id);
         Print("[AUTO TRADE] ORDER_SENT order_id=",order_id," symbol=",execSymbol," retcode=",retcode," deal=",(long)deal," order=",(long)ord);
         SendReport(order_id,dir,"ORDER_SENT",execSymbol,StringFormat("retcode=%u deal=%I64u order=%I64u %s",retcode,deal,ord,desc));
      }
      else
      {
         // Only successful orders enter the local duplicate guard; transient failures can retry from the backend.
         Print("[AUTO TRADE] ORDER_FAILED order_id=",order_id," symbol=",execSymbol," retcode=",retcode," desc=",desc);
         SendReport(order_id,dir,"ORDER_FAILED",execSymbol,StringFormat("retcode=%u deal=%I64u order=%I64u %s",retcode,deal,ord,desc));
      }

      pos+=MathMax(1,StringLen(order_id));
   }
   return true;
}

void OnTimer()
{
   SXHandleTP1TP2();

   RefreshSession();
   if(g_last_state==0 || (TimeCurrent()-g_last_state)>=StateSeconds)
   {
      ReportState();
      g_last_state=TimeCurrent();
   }

   string xau=XAUStateSymbol();
   PollMarket("XAU/USD",xau);
}
